# Prod outputs are printed in public CI logs, so nothing here carries an account ID.

output "vector_bucket" {
  value = aws_s3vectors_vector_bucket.main.vector_bucket_name
}

output "indexes" {
  value = {
    response_cache = aws_s3vectors_index.response_cache.index_name
    sources        = aws_s3vectors_index.sources.index_name
  }
}

output "tables" {
  value = {
    logs       = aws_dynamodb_table.logs.name
    ratelimits = aws_dynamodb_table.ratelimits.name
  }
}

output "site_url" {
  value = var.create_hosting ? "https://${module.hosting[0].fqdn}" : null
}

output "function_name" {
  value = var.create_hosting ? module.hosting[0].function_name : null
}

output "ui_bucket" {
  value     = var.create_hosting ? module.hosting[0].ui_bucket : null
  sensitive = true # the name contains the account ID
}

output "distribution_id" {
  value     = var.create_hosting ? module.hosting[0].distribution_id : null
  sensitive = true
}
