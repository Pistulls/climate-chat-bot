variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "domain_name" {
  type        = string
  description = "Parent domain owned by the website repo, e.g. example.dev."
}

variable "subdomain" {
  type    = string
  default = "climate-chat"
}

variable "state_bucket" {
  type        = string
  description = "Terraform state bucket shared with the website repo. Only the climate-chat/prod/ prefix is granted to CI."
}

variable "github_oidc_sub_prefix" {
  type        = string
  description = "OIDC subject prefix of this repo: gh api repos/<owner>/climate-chatter/actions/oidc/customization/sub --jq .sub_claim_prefix"
}

variable "budget_email" {
  type        = string
  description = "Where AWS Budgets sends cost alerts."
}

variable "budget_limit_usd" {
  type    = number
  default = 5
}
