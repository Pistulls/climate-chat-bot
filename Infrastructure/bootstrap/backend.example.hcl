# Copy to backend.local.hcl (gitignored) and fill in.
bucket       = "<state-bucket>"
key          = "climate-chat/bootstrap/terraform.tfstate"
region       = "eu-west-2"
encrypt      = true
use_lockfile = true
