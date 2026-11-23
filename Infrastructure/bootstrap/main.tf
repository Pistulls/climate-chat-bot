data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  fqdn       = "${var.subdomain}.${var.domain_name}" # climate-chat.<domain>
}
