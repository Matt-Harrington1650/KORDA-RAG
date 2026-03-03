variable "environment" {
  description = "Environment name."
  type        = string
}

variable "secret_prefix" {
  description = "Secret namespace prefix."
  type        = string
  default     = "korda-rag"
}

variable "kms_key_arn" {
  description = "Optional KMS key ARN for secret encryption."
  type        = string
  default     = null
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
