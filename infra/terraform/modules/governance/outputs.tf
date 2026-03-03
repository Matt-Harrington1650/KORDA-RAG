output "kms_key_arn" {
  description = "KMS key ARN used for platform encryption."
  value       = aws_kms_key.platform.arn
}

output "audit_bucket_name" {
  description = "CloudTrail audit bucket name."
  value       = aws_s3_bucket.audit.id
}

output "backup_bucket_name" {
  description = "Backup bucket name."
  value       = aws_s3_bucket.backup.id
}

output "backup_bucket_arn" {
  description = "Backup bucket ARN."
  value       = aws_s3_bucket.backup.arn
}

output "cloudtrail_name" {
  description = "CloudTrail name."
  value       = var.enable_cloudtrail ? aws_cloudtrail.audit[0].name : null
}

output "eks_audit_log_group_name" {
  description = "EKS audit log group name."
  value       = aws_cloudwatch_log_group.eks_audit.name
}
