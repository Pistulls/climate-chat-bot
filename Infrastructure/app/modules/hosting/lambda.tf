locals {
  function_name = "${var.name_prefix}-api"
}

# Placeholder code. The service's own deploy replaces it; Terraform ignores code changes.
data "archive_file" "placeholder" {
  type        = "zip"
  source_file = "${path.module}/placeholder/handler.py"
  output_path = "${path.module}/.build/placeholder.zip"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = local.function_name
  description        = "Execution role for ${local.function_name}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  # Query needs GetVectors as well when it returns metadata.
  statement {
    sid       = "VectorRead"
    actions   = ["s3vectors:QueryVectors", "s3vectors:GetVectors"]
    resources = [var.data_stores.cache_index_arn, var.data_stores.sources_index_arn]
  }

  # Only the cache is written by the service; sources are written by ingestion.
  statement {
    sid       = "CacheWrite"
    actions   = ["s3vectors:PutVectors"]
    resources = [var.data_stores.cache_index_arn]
  }

  statement {
    sid       = "LogWrite"
    actions   = ["dynamodb:PutItem"]
    resources = [var.data_stores.logs_table_arn]
  }

  statement {
    sid       = "RateLimits"
    actions   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
    resources = [var.data_stores.ratelimits_table_arn]
  }

  statement {
    sid       = "Secrets"
    actions   = ["ssm:GetParameter"]
    resources = [for name in var.ssm_parameter_names : "arn:aws:ssm:${var.region}:${var.account_id}:parameter${name}"]
  }

  # Embeddings (plan 06): Bedrock models only, and only the configured one.
  dynamic "statement" {
    for_each = startswith(var.embedding_model, "amazon.") ? [var.embedding_model] : []
    content {
      sid       = "Embeddings"
      actions   = ["bedrock:InvokeModel"]
      resources = ["arn:aws:bedrock:${var.region}::foundation-model/${statement.value}"]
    }
  }

  # SecureStrings use the AWS-managed aws/ssm key; only allow decrypting through SSM.
  statement {
    sid       = "SecretsDecrypt"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.region}:${var.account_id}:key/*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  function_name = local.function_name
  description   = "Climate Chat API (/api/*)"
  role          = aws_iam_role.api.arn
  runtime       = var.lambda.runtime
  architectures = ["arm64"]
  handler       = "handler.handler"
  memory_size   = var.lambda.memory_mb
  timeout       = var.lambda.timeout_s

  reserved_concurrent_executions = var.lambda.concurrency

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = var.environment
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash] # the service deploy owns the code
  }

  depends_on = [aws_iam_role_policy.api]
}

# IAM auth: only callers with a signature get in, and only CloudFront (via OAC) is allowed.
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
}

# Function URLs need both permissions for the caller.
resource "aws_lambda_permission" "cloudfront_url" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.main.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke" {
  statement_id             = "AllowCloudFrontInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.main.arn
  invoked_via_function_url = true
}
