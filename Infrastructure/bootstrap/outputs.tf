# Bootstrap is applied locally, never in CI, so these don't reach public Actions logs.

output "name_servers" {
  description = "Values for the NS delegation record in the website repo."
  value       = aws_route53_zone.main.name_servers
}

output "zone_id" {
  value = aws_route53_zone.main.zone_id
}

output "certificate_arn" {
  value = aws_acm_certificate_validation.main.certificate_arn
}

output "github_deploy_role_arn" {
  description = "Store as the AWS_DEPLOY_ROLE_ARN Actions secret."
  value       = aws_iam_role.github_deploy.arn
}

output "ssm_parameter_names" {
  value = local.secure_parameters
}
