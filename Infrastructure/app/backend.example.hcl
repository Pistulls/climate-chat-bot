# Copy to backend.dev.local.hcl / backend.prod.local.hcl (gitignored) and fill in.
bucket       = "<state-bucket>"
key          = "climate-chat/<env>/terraform.tfstate"
region       = "eu-west-2"
encrypt      = true
use_lockfile = true
