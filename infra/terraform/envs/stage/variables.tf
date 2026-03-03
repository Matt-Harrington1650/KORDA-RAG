variable "environment" {
  description = "Environment name."
  type        = string
  default     = "stage"
}

variable "aws_region" {
  description = "AWS region for deployment."
  type        = string
  default     = "us-west-2"

  validation {
    condition = contains([
      "us-east-1",
      "us-east-2",
      "us-west-1",
      "us-west-2"
    ], var.aws_region)
    error_message = "aws_region must be a US region."
  }
}

variable "account_id" {
  description = "Expected AWS account ID. Leave blank to use current caller account."
  type        = string
  default     = ""
}

variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
  default     = "korda-rag-stage"
}

variable "namespace" {
  description = "Namespace for KORDA workloads."
  type        = string
  default     = "rag-stage"
}

variable "vpc_cidr" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.50.0.0/16"
}

variable "az_count" {
  description = "Number of AZs."
  type        = number
  default     = 3
}

variable "kubernetes_version" {
  description = "Kubernetes version."
  type        = string
  default     = "1.30"
}

variable "enable_single_nat_gateway" {
  description = "Use one NAT gateway for cost optimization."
  type        = bool
  default     = true
}

variable "cpu_node_instance_types" {
  description = "CPU node group instance types."
  type        = list(string)
  default     = ["m7i.2xlarge"]
}

variable "gpu_node_instance_types" {
  description = "GPU node group instance types."
  type        = list(string)
  default     = ["g5.2xlarge"]
}

variable "cpu_min_size" {
  type    = number
  default = 2
}

variable "cpu_max_size" {
  type    = number
  default = 8
}

variable "cpu_desired_size" {
  type    = number
  default = 4
}

variable "gpu_min_size" {
  type    = number
  default = 1
}

variable "gpu_max_size" {
  type    = number
  default = 3
}

variable "gpu_desired_size" {
  type    = number
  default = 1
}

variable "common_tags" {
  description = "Additional custom tags."
  type        = map(string)
  default     = {}
}
