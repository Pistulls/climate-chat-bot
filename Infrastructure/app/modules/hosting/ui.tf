# Static Solid build. Only CloudFront (via OAC) reads it. Content is synced by the UI
# deploy; Terraform only seeds a placeholder index.html.
resource "aws_s3_bucket" "ui" {
  bucket = "${var.name_prefix}-ui-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "ui" {
  bucket                  = aws_s3_bucket.ui.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "ui" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.ui.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }

  # Lets S3 answer 404 rather than 403 for a missing asset.
  statement {
    sid       = "AllowCloudFrontNotFound"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.ui.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "ui" {
  bucket     = aws_s3_bucket.ui.id
  policy     = data.aws_iam_policy_document.ui.json
  depends_on = [aws_s3_bucket_public_access_block.ui]
}

resource "aws_s3_object" "placeholder_index" {
  bucket        = aws_s3_bucket.ui.id
  key           = "index.html"
  source        = "${path.module}/placeholder/index.html"
  content_type  = "text/html; charset=utf-8"
  cache_control = "no-cache"

  lifecycle {
    ignore_changes = all # the UI deploy owns the content after the first apply
  }
}
