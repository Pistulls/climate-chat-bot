data "aws_caller_identity" "current" {}

locals {
  name_prefix = "climate-chat-${var.env}" # climate-chat-dev / climate-chat-prod

  # Created by Infrastructure/bootstrap; values are set outside Terraform.
  ssm_parameters = {
    openrouter_api_key   = "/climate-chat/${var.env}/openrouter-api-key"
    turnstile_secret_key = "/climate-chat/${var.env}/turnstile-secret-key"
  }
}

check "hosting_needs_domain" {
  assert {
    condition     = !var.create_hosting || var.domain_name != null
    error_message = "domain_name must be set when create_hosting is true."
  }
}
