variable "env" {
  type = string
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod."
  }
}

variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "create_hosting" {
  type        = bool
  description = "Lambda, UI bucket, CloudFront and DNS. Off for dev, where the service and UI run locally."
  default     = false
}

# --- Personal values: set in <env>.local.tfvars (gitignored) or TF_VAR_* in CI ---

variable "domain_name" {
  type        = string
  description = "Parent domain, e.g. example.dev. Only used when create_hosting is true."
  default     = null
}

variable "subdomain" {
  type    = string
  default = "climate-chat"
}

# --- Vector indexes ---

variable "embedding_dimension" {
  type        = number
  description = "Must match the embedding model. Changing it replaces both indexes and needs a re-ingest."
}

# --- Service settings (passed to the Lambda as environment variables) ---

variable "models" {
  type = object({
    classify  = string
    facts     = string
    reply     = string
    fallback  = string
    embedding = string
  })
}

variable "limits" {
  type = object({
    requests_per_minute = number
    requests_per_day    = number
    max_comment_chars   = number
    log_ttl_days        = number
  })
  default = {
    requests_per_minute = 10
    requests_per_day    = 100
    max_comment_chars   = 1000
    log_ttl_days        = 90
  }
}

# Tuned in plan 03 (Phase 4); see Project/Design.md, LLM. The code has the same defaults.
variable "service" {
  type = object({
    max_tokens_classify = number
    max_tokens_facts    = number
    max_tokens_reply    = number
    cache_max_distance  = number       # cosine distance for a response-cache hit
    excluded_licences   = list(string) # licence values the Facts Search must not quote
  })
  default = {
    max_tokens_classify = 200
    max_tokens_facts    = 1000
    max_tokens_reply    = 300
    cache_max_distance  = 0.15
    excluded_licences   = [] # decided before launch (plan 04)
  }
}

variable "lambda" {
  type = object({
    runtime     = string
    memory_mb   = number
    timeout_s   = number
    concurrency = number # -1 = unreserved. Needs an account quota above 10 to set.
  })
  default = {
    runtime     = "python3.14"
    memory_mb   = 512
    timeout_s   = 30
    concurrency = -1
  }
}
