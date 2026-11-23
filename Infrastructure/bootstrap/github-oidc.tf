# The OIDC provider already exists in this account (created once by the website repo).
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# Only workflow runs on main in this repo, matched by immutable owner/repo IDs.
# PR runs get a different `sub`, so they can't assume it.
data "aws_iam_policy_document" "github_deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_sub_prefix}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "github-deploy-climate-chat"
  description          = "Assumed by GitHub Actions on main to apply Infrastructure/app for prod"
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_trust.json
  max_session_duration = 3600
}

locals {
  prod_prefix = "climate-chat-prod" # every prod resource name starts with this
  arn_region  = "${var.region}:${local.account_id}"
}

data "aws_iam_policy_document" "github_deploy" {
  # --- Terraform state: the prod app key only ---
  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["climate-chat/prod/*"]
    }
  }
  statement {
    sid       = "StateReadWrite"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"] # Delete releases the .tflock
    resources = ["arn:aws:s3:::${var.state_bucket}/climate-chat/prod/*"]
  }

  # --- S3 Vectors: configuration of the prod bucket and its indexes, no vector data ---
  statement {
    sid = "VectorConfig"
    actions = [
      "s3vectors:CreateVectorBucket",
      "s3vectors:DeleteVectorBucket",
      "s3vectors:GetVectorBucket",
      "s3vectors:CreateIndex",
      "s3vectors:DeleteIndex",
      "s3vectors:GetIndex",
      "s3vectors:ListIndexes",
      "s3vectors:TagResource",
      "s3vectors:UntagResource",
      "s3vectors:ListTagsForResource",
    ]
    resources = [
      "arn:aws:s3vectors:${local.arn_region}:bucket/${local.prod_prefix}-vectors",
      "arn:aws:s3vectors:${local.arn_region}:bucket/${local.prod_prefix}-vectors/index/*",
    ]
  }

  # --- DynamoDB: table configuration only, no item access ---
  statement {
    sid = "DynamoTables"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeTable",
      "dynamodb:UpdateTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:UpdateTimeToLive",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:ListTagsOfResource",
    ]
    resources = ["arn:aws:dynamodb:${local.arn_region}:table/${local.prod_prefix}-*"]
  }

  # --- Lambda ---
  statement {
    sid = "Lambda"
    actions = [
      "lambda:Get*",
      "lambda:List*",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:UpdateFunctionConfiguration",
      "lambda:UpdateFunctionCode",
      "lambda:PutFunctionConcurrency",
      "lambda:DeleteFunctionConcurrency",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:CreateFunctionUrlConfig",
      "lambda:UpdateFunctionUrlConfig",
      "lambda:DeleteFunctionUrlConfig",
      "lambda:TagResource",
      "lambda:UntagResource",
    ]
    resources = ["arn:aws:lambda:${local.arn_region}:function:${local.prod_prefix}-*"]
  }

  # --- IAM: only the prod execution roles, and only passable to Lambda ---
  statement {
    sid = "ExecutionRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.prod_prefix}-*"]
  }
  statement {
    sid       = "PassExecutionRole"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.prod_prefix}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  # --- CloudWatch Logs: the function's log group ---
  statement {
    sid       = "LogGroupLookup"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    sid = "LogGroup"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
      "logs:ListTagsForResource",
    ]
    resources = [
      "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${local.prod_prefix}-*",
      "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${local.prod_prefix}-*:*",
    ]
  }

  # --- UI bucket: manage it and its objects, but never delete the bucket ---
  statement {
    sid     = "UiBucket"
    actions = ["s3:Get*", "s3:List*", "s3:Put*", "s3:CreateBucket", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${local.prod_prefix}-ui-*",
      "arn:aws:s3:::${local.prod_prefix}-ui-*/*",
    ]
  }

  # --- CloudFront: distribution ARNs use generated IDs, so writes can't be narrowed to
  # ours by name. No DeleteDistribution, as for the website's role. ---
  statement {
    sid       = "CloudFrontRead"
    actions   = ["cloudfront:Get*", "cloudfront:List*", "cloudfront:DescribeFunction"]
    resources = ["*"]
  }
  statement {
    sid = "CloudFrontWrite"
    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:UpdateDistribution",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:CreateInvalidation",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:UpdateOriginAccessControl",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:CreateFunction",
      "cloudfront:UpdateFunction",
      "cloudfront:PublishFunction",
      "cloudfront:DeleteFunction",
      "cloudfront:CreateOriginRequestPolicy",
      "cloudfront:UpdateOriginRequestPolicy",
      "cloudfront:DeleteOriginRequestPolicy",
      "cloudfront:CreateResponseHeadersPolicy",
      "cloudfront:UpdateResponseHeadersPolicy",
      "cloudfront:DeleteResponseHeadersPolicy",
    ]
    resources = [
      "arn:aws:cloudfront::${local.account_id}:distribution/*",
      "arn:aws:cloudfront::${local.account_id}:origin-access-control/*",
      "arn:aws:cloudfront::${local.account_id}:function/*",
      "arn:aws:cloudfront::${local.account_id}:origin-request-policy/*",
      "arn:aws:cloudfront::${local.account_id}:response-headers-policy/*",
    ]
  }

  # --- Route 53: records in this project's zone only ---
  statement {
    sid       = "DnsLookup"
    actions   = ["route53:ListHostedZones", "route53:ListHostedZonesByName", "route53:GetChange"]
    resources = ["*"]
  }
  statement {
    sid = "DnsRecords"
    actions = [
      "route53:GetHostedZone",
      "route53:ListResourceRecordSets",
      "route53:ChangeResourceRecordSets",
      "route53:ListTagsForResource",
    ]
    resources = [aws_route53_zone.main.arn]
  }

  # --- ACM: read-only, to find the certificate ---
  statement {
    sid       = "CertificateLookup"
    actions   = ["acm:ListCertificates", "acm:DescribeCertificate", "acm:GetCertificate", "acm:ListTagsForCertificate"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy-climate-chat-prod"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
