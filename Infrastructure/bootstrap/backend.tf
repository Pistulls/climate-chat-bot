# Partial config: the bucket name contains the account ID, so it stays out of this
# public repo. Supply it with:
#   terraform init -backend-config=backend.local.hcl
# (copy backend.example.hcl to backend.local.hcl, which is gitignored).
terraform {
  backend "s3" {}
}
