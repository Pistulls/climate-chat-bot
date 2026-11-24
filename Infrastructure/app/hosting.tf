module "hosting" {
  source = "./modules/hosting"
  count  = var.create_hosting ? 1 : 0

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix = local.name_prefix
  region      = var.region
  account_id  = data.aws_caller_identity.current.account_id
  fqdn        = "${var.subdomain}.${coalesce(var.domain_name, "unset.invalid")}"
  lambda      = var.lambda

  ssm_parameter_names = values(local.ssm_parameters)

  data_stores = {
    logs_table_arn       = aws_dynamodb_table.logs.arn
    ratelimits_table_arn = aws_dynamodb_table.ratelimits.arn
    cache_index_arn      = aws_s3vectors_index.response_cache.index_arn
    sources_index_arn    = aws_s3vectors_index.sources.index_arn
  }

  # Config, not secrets: secrets are fetched from SSM at runtime by parameter name.
  # EXCLUDED_LICENCES is only set when the list is non-empty: an empty value would show as a
  # permanent diff, and the service treats unset as "no filter".
  environment = merge({
    APP_ENV                = var.env
    LOGS_TABLE             = aws_dynamodb_table.logs.name
    RATELIMITS_TABLE       = aws_dynamodb_table.ratelimits.name
    VECTOR_BUCKET          = aws_s3vectors_vector_bucket.main.vector_bucket_name
    CACHE_INDEX            = aws_s3vectors_index.response_cache.index_name
    SOURCES_INDEX          = aws_s3vectors_index.sources.index_name
    OPENROUTER_KEY_PARAM   = local.ssm_parameters.openrouter_api_key
    TURNSTILE_SECRET_PARAM = local.ssm_parameters.turnstile_secret_key
    LOG_HASH_KEY_PARAM     = local.ssm_parameters.log_hash_key
    MODEL_CLASSIFY         = var.models.classify
    MODEL_FACTS            = var.models.facts
    MODEL_REPLY            = var.models.reply
    MODEL_FALLBACK         = var.models.fallback
    MODEL_EMBEDDING        = var.models.embedding
    EMBEDDING_DIMENSION    = tostring(var.embedding_dimension)
    RATE_LIMIT_PER_MINUTE  = tostring(var.limits.requests_per_minute)
    RATE_LIMIT_PER_DAY     = tostring(var.limits.requests_per_day)
    MAX_COMMENT_CHARS      = tostring(var.limits.max_comment_chars)
    LOG_TTL_DAYS           = tostring(var.limits.log_ttl_days)
    CLIENT_IP_HEADER       = "cloudfront-viewer-address"
    MAX_TOKENS_CLASSIFY    = tostring(var.service.max_tokens_classify)
    MAX_TOKENS_FACTS       = tostring(var.service.max_tokens_facts)
    MAX_TOKENS_REPLY       = tostring(var.service.max_tokens_reply)
    CACHE_MAX_DISTANCE     = tostring(var.service.cache_max_distance)
    },
    length(var.service.excluded_licences) > 0 ? { EXCLUDED_LICENCES = join(",", var.service.excluded_licences) } : {},
  )
}
