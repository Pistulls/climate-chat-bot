terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73" # S3 Vectors resources and Lambda URL invoke permissions
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "climate-chat"
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}

# CloudFront certificates live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "climate-chat"
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}
