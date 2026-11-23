# Partial config, one state file per env. The bucket name stays out of this public repo:
#   terraform init -reconfigure -backend-config=backend.<env>.local.hcl
# (copy backend.example.hcl; *.local.hcl is gitignored). CI writes its own.
terraform {
  backend "s3" {}
}
