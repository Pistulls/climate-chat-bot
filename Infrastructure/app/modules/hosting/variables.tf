variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "account_id" {
  type = string
}

variable "embedding_model" {
  type        = string
  description = "Embedding model id; ids starting amazon. are called through Bedrock"
}

variable "fqdn" {
  type        = string
  description = "climate-chat.<domain>. Its hosted zone and ACM certificate come from Infrastructure/bootstrap."
}

variable "lambda" {
  type = object({
    runtime     = string
    memory_mb   = number
    timeout_s   = number
    concurrency = number
  })
}

variable "environment" {
  type        = map(string)
  description = "Lambda environment variables. Never secrets."
}

variable "ssm_parameter_names" {
  type        = list(string)
  description = "SecureString parameters the function may read."
}

variable "data_stores" {
  type = object({
    logs_table_arn       = string
    ratelimits_table_arn = string
    cache_index_arn      = string
    sources_index_arn    = string
  })
}
