# On-demand, AWS-owned encryption key (the default), no PITR: logs and counters can be lost.
# Item layout is the service's business; generic string keys keep it open.

resource "aws_dynamodb_table" "logs" {
  name                        = "${local.name_prefix}-logs"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = var.env == "prod"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at" # epoch seconds
    enabled        = true
  }
}

# One counter item per IP per window, e.g. pk = "ip#<ip>#min#<window>".
resource "aws_dynamodb_table" "ratelimits" {
  name                        = "${local.name_prefix}-ratelimits"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  deletion_protection_enabled = var.env == "prod"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
