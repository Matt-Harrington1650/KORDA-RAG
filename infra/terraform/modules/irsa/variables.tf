variable "environment" {
  description = "Environment name."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace where RAG workloads run."
  type        = string
  default     = "rag"
}

variable "oidc_provider_arn" {
  description = "OIDC provider ARN."
  type        = string
}

variable "secrets_arns" {
  description = "Secret ARNs that workloads can read."
  type        = list(string)
}

variable "backup_bucket_arn" {
  description = "Backup bucket ARN."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used for encrypted secret access."
  type        = string
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
