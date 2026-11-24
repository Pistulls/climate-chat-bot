# Terraform creates the parameters, never the values: a value set here would sit in
# plain text in the state file. Set each one once, outside Terraform:
#   aws ssm put-parameter --name <name> --type SecureString --value "<key>" --overwrite
locals {
  secure_parameters = {
    prod_openrouter   = "/climate-chat/prod/openrouter-api-key"
    prod_turnstile    = "/climate-chat/prod/turnstile-secret-key"
    dev_openrouter    = "/climate-chat/dev/openrouter-api-key"
    ingest_openrouter = "/climate-chat/ingest/openrouter-api-key"
    # HMAC key for the hashed user ids in the request logs (Project/Design.md, Request logs).
    prod_log_hash = "/climate-chat/prod/log-hash-key"
    dev_log_hash  = "/climate-chat/dev/log-hash-key"
  }
}

resource "aws_ssm_parameter" "secret" {
  for_each = local.secure_parameters

  name  = each.value
  type  = "SecureString" # encrypted with the AWS-managed aws/ssm key
  tier  = "Standard"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
