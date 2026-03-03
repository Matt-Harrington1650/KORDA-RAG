output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_ca_data" {
  value = module.eks.cluster_certificate_authority_data
}

output "oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "secret_names" {
  value = module.secrets.secret_names
}

output "secret_arns" {
  value = module.secrets.secret_arns
}

output "irsa_role_arns" {
  value = module.irsa.role_arns
}

output "backup_bucket_name" {
  value = module.governance.backup_bucket_name
}

output "audit_bucket_name" {
  value = module.governance.audit_bucket_name
}
