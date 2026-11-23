# Copy to bootstrap.local.tfvars (gitignored) and fill in:
#   terraform plan -var-file=bootstrap.local.tfvars
domain_name            = "<domain>"
state_bucket           = "<state-bucket>"
github_oidc_sub_prefix = "repo:<owner>@<owner_id>/climate-chatter@<repo_id>"
budget_email           = "<email>"
