module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = var.enable_public_endpoint

  create_cloudwatch_log_group            = true
  cloudwatch_log_group_retention_in_days = var.cluster_log_retention_days
  cluster_enabled_log_types              = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  enable_irsa = true

  cluster_encryption_config = {
    resources        = ["secrets"]
    provider_key_arn = var.kms_key_arn
  }

  cluster_addons = {
    coredns = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
    aws-ebs-csi-driver = {}
  }

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_group_defaults = {
    ami_type  = "AL2023_x86_64_STANDARD"
    disk_size = 200
  }

  eks_managed_node_groups = {
    cpu = {
      instance_types = var.cpu_node_instance_types
      min_size       = var.cpu_min_size
      max_size       = var.cpu_max_size
      desired_size   = var.cpu_desired_size
      labels = {
        workload = "general"
      }
    }

    gpu = {
      ami_type       = "AL2_x86_64_GPU"
      instance_types = var.gpu_node_instance_types
      min_size       = var.gpu_min_size
      max_size       = var.gpu_max_size
      desired_size   = var.gpu_desired_size
      labels = {
        workload = "gpu"
      }
      taints = {
        gpu_only = {
          key    = "dedicated"
          value  = "gpu"
          effect = "NO_SCHEDULE"
        }
      }
    }
  }

  tags = var.tags
}
