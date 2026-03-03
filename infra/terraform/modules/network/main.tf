data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  public_subnets = [
    for idx, _ in local.azs :
    cidrsubnet(var.cidr_block, var.public_subnet_newbits, idx)
  ]

  private_subnets = [
    for idx, _ in local.azs :
    cidrsubnet(var.cidr_block, var.private_subnet_newbits, idx + 32)
  ]

  intra_subnets = [
    for idx, _ in local.azs :
    cidrsubnet(var.cidr_block, var.intra_subnet_newbits, idx + 64)
  ]
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "${var.name_prefix}-vpc"
  cidr = var.cidr_block

  azs            = local.azs
  public_subnets = local.public_subnets
  private_subnets = local.private_subnets
  intra_subnets  = local.intra_subnets

  enable_nat_gateway = true
  single_nat_gateway = var.enable_single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  map_public_ip_on_launch = false

  tags = var.tags
}
