# climate-chat.<domain>  ->  CloudFront
#                              /*      -> S3 UI bucket (OAC)
#                              /api/*  -> Lambda function URL (OAC)

data "aws_acm_certificate" "main" {
  provider    = aws.us_east_1
  domain      = var.fqdn
  statuses    = ["ISSUED"]
  most_recent = true
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

resource "aws_cloudfront_origin_access_control" "ui" {
  name                              = "${var.name_prefix}-ui"
  description                       = "CloudFront -> UI bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# POST bodies aren't signed by CloudFront: the browser must send x-amz-content-sha256
# (hex SHA-256 of the body) or the function URL rejects the signature.
resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "${var.name_prefix}-api"
  description                       = "CloudFront -> Lambda function URL"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# A named list rather than the managed AllViewerExceptHostHeader policy: that one
# doesn't forward CloudFront-* headers, and the rate limiter needs the viewer's IP.
# Host is never forwarded (the function URL rejects a foreign Host). X-Amz-* headers
# can't be listed here (CloudFront rejects them); OAC reads the viewer's
# x-amz-content-sha256 itself when it signs the origin request.
resource "aws_cloudfront_origin_request_policy" "api" {
  name    = "${var.name_prefix}-api"
  comment = "Headers the API needs, plus the viewer's IP"

  headers_config {
    header_behavior = "whitelist"
    headers {
      items = [
        "Accept",
        "Content-Type",
        "Origin",
        "CloudFront-Viewer-Address",
        "CloudFront-Viewer-Country",
        # The key for GET /api/logs. A custom header because OAC signing replaces any
        # viewer Authorization header.
        "X-Admin-Key",
      ]
    }
  }

  query_strings_config {
    query_string_behavior = "all"
  }

  cookies_config {
    cookie_behavior = "none"
  }
}

resource "aws_cloudfront_response_headers_policy" "security" {
  name    = "${var.name_prefix}-security"
  comment = "Security headers; CSP allows Cloudflare Turnstile"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = false
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }

    content_security_policy {
      content_security_policy = join("; ", [
        "default-src 'self'",
        "script-src 'self' https://challenges.cloudflare.com",
        "frame-src https://challenges.cloudflare.com",
        "connect-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
      ])
      override = true
    }
  }
}

resource "aws_cloudfront_function" "spa_router" {
  name    = "${var.name_prefix}-spa-router"
  runtime = "cloudfront-js-2.0"
  comment = "Extensionless paths -> /index.html"
  publish = true
  code    = file("${path.module}/functions/spa-router.js")
}

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  comment             = "Climate Chat (${var.fqdn})"
  aliases             = [var.fqdn]
  price_class         = "PriceClass_100" # Europe and North America edges only
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  default_root_object = "index.html"

  origin {
    origin_id                = "ui"
    domain_name              = aws_s3_bucket.ui.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.ui.id
  }

  origin {
    origin_id                = "api"
    domain_name              = split("/", aws_lambda_function_url.api.function_url)[2] # <id>.lambda-url.<region>.on.aws
    origin_access_control_id = aws_cloudfront_origin_access_control.api.id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 30
    }
  }

  default_cache_behavior {
    target_origin_id           = "ui"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
    compress                   = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_router.arn
    }
  }

  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = "api"
    viewer_protocol_policy     = "https-only"
    allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id   = aws_cloudfront_origin_request_policy.api.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
    compress                   = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.main.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
