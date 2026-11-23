output "fqdn" {
  value = var.fqdn
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "ui_bucket" {
  value = aws_s3_bucket.ui.bucket
}

output "distribution_id" {
  value = aws_cloudfront_distribution.main.id
}
