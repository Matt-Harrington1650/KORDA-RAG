data "aws_caller_identity" "current" {}

locals {
  resolved_account_id = var.account_id != "" ? var.account_id : data.aws_caller_identity.current.account_id
  tags = merge({
    Project     = "korda-rag"
    Environment = var.environment
    ManagedBy   = "terraform"
    Compliance  = "regulated-ready"
    DataRegion  = "us-only"
  }, var.common_tags)
}

module "network" {
  source = "../../modules/network"

  name_prefix               = var.cluster_name
  cidr_block                = var.vpc_cidr
  az_count                  = var.az_count
  enable_single_nat_gateway = var.enable_single_nat_gateway
  tags                      = local.tags
}

module "governance" {
  source = "../../modules/governance"

  environment            = var.environment
  account_id             = local.resolved_account_id
  region                 = var.aws_region
  eks_log_retention_days = 90
  backup_retention_days  = 30
  enable_cloudtrail      = true
  tags                   = local.tags
}

module "eks" {
  source = "../../modules/eks"

  cluster_name             = var.cluster_name
  kubernetes_version       = var.kubernetes_version
  vpc_id                   = module.network.vpc_id
  private_subnet_ids       = module.network.private_subnet_ids
  kms_key_arn              = module.governance.kms_key_arn
  cluster_log_retention_days = 90
  enable_public_endpoint   = false

  cpu_node_instance_types = var.cpu_node_instance_types
  gpu_node_instance_types = var.gpu_node_instance_types
  cpu_min_size            = var.cpu_min_size
  cpu_max_size            = var.cpu_max_size
  cpu_desired_size        = var.cpu_desired_size
  gpu_min_size            = var.gpu_min_size
  gpu_max_size            = var.gpu_max_size
  gpu_desired_size        = var.gpu_desired_size
  tags                    = local.tags
}

module "secrets" {
  source = "../../modules/secrets"

  environment = var.environment
  kms_key_arn = module.governance.kms_key_arn
  tags        = local.tags
}

module "irsa" {
  source = "../../modules/irsa"

  environment       = var.environment
  namespace         = var.namespace
  oidc_provider_arn = module.eks.oidc_provider_arn
  secrets_arns      = values(module.secrets.secret_arns)
  backup_bucket_arn = module.governance.backup_bucket_arn
  kms_key_arn       = module.governance.kms_key_arn
  tags              = local.tags
}
