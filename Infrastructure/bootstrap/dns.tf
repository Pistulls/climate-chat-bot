# The project's own zone. The website repo delegates to it with one NS record,
# which hard-codes these name servers, so the zone must never be recreated.
resource "aws_route53_zone" "main" {
  name    = local.fqdn
  comment = "Climate Chat, delegated from the parent ${var.domain_name} zone"

  lifecycle {
    prevent_destroy = true
  }
}

# Own CAA record, so certificate issuance doesn't depend on the parent zone's.
resource "aws_route53_record" "caa" {
  zone_id = aws_route53_zone.main.zone_id
  name    = local.fqdn
  type    = "CAA"
  ttl     = 3600
  records = [
    "0 issue \"amazon.com\"",
    "0 issuewild \";\"",
  ]
}
