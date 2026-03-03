variable "environment" {
  description = "Environment name."
  type        = string
}

variable "account_id" {
  description = "AWS account ID."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "bucket_name_prefix" {
  description = "Bucket name prefix."
  type        = string
  default     = "korda-rag"
}

variable "eks_log_retention_days" {
  description = "Retention for EKS audit log groups."
  type        = number
  default     = 90
}

variable "backup_retention_days" {
  description = "Object expiration for backup bucket."
  type        = number
  default     = 30
}

variable "enable_cloudtrail" {
  description = "Enable CloudTrail trail."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
