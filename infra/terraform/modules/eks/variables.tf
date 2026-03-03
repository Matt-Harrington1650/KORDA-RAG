variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version."
  type        = string
  default     = "1.30"
}

variable "vpc_id" {
  description = "VPC ID."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS nodes."
  type        = list(string)
}

variable "kms_key_arn" {
  description = "KMS key ARN for Kubernetes secret encryption."
  type        = string
}

variable "cluster_log_retention_days" {
  description = "Retention for EKS control plane logs."
  type        = number
  default     = 90
}

variable "enable_public_endpoint" {
  description = "Enable public EKS API endpoint."
  type        = bool
  default     = false
}

variable "cpu_node_instance_types" {
  description = "Instance types for CPU node group."
  type        = list(string)
  default     = ["m7i.2xlarge"]
}

variable "gpu_node_instance_types" {
  description = "Instance types for GPU node group."
  type        = list(string)
  default     = ["g5.2xlarge"]
}

variable "cpu_min_size" {
  description = "Minimum CPU node count."
  type        = number
  default     = 2
}

variable "cpu_max_size" {
  description = "Maximum CPU node count."
  type        = number
  default     = 6
}

variable "cpu_desired_size" {
  description = "Desired CPU node count."
  type        = number
  default     = 3
}

variable "gpu_min_size" {
  description = "Minimum GPU node count."
  type        = number
  default     = 1
}

variable "gpu_max_size" {
  description = "Maximum GPU node count."
  type        = number
  default     = 3
}

variable "gpu_desired_size" {
  description = "Desired GPU node count."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
