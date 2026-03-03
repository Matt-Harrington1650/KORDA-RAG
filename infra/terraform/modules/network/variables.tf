variable "name_prefix" {
  description = "Name prefix used for VPC resources."
  type        = string
}

variable "cidr_block" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of AZs to use."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 4
    error_message = "az_count must be between 2 and 4."
  }
}

variable "enable_single_nat_gateway" {
  description = "Whether to use a single NAT gateway."
  type        = bool
  default     = true
}

variable "public_subnet_newbits" {
  description = "Additional subnet bits used for public subnets."
  type        = number
  default     = 8
}

variable "private_subnet_newbits" {
  description = "Additional subnet bits used for private subnets."
  type        = number
  default     = 8
}

variable "intra_subnet_newbits" {
  description = "Additional subnet bits used for intra subnets."
  type        = number
  default     = 8
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
