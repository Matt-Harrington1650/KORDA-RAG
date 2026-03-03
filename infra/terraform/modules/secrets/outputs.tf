output "secret_arns" {
  description = "Managed secret ARNs keyed by logical secret name."
  value       = { for k, v in aws_secretsmanager_secret.managed : k => v.arn }
}

output "secret_names" {
  description = "Managed secret names keyed by logical secret name."
  value       = { for k, v in aws_secretsmanager_secret.managed : k => v.name }
}
