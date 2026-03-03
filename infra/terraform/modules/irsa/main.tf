data "aws_iam_policy_document" "rag_runtime" {
  statement {
    sid = "ReadServiceSecrets"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = var.secrets_arns
  }

  statement {
    sid = "DecryptSecrets"
    actions = [
      "kms:Decrypt"
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_policy" "rag_runtime" {
  name_prefix = "korda-rag-${var.environment}-rag-runtime-"
  policy      = data.aws_iam_policy_document.rag_runtime.json
  tags        = var.tags
}

data "aws_iam_policy_document" "ingestor_runtime" {
  statement {
    sid = "ReadServiceSecrets"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = var.secrets_arns
  }

  statement {
    sid = "DecryptSecrets"
    actions = [
      "kms:Decrypt"
    ]
    resources = [var.kms_key_arn]
  }

  statement {
    sid = "BackupBucketAccess"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      var.backup_bucket_arn,
      "${var.backup_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_policy" "ingestor_runtime" {
  name_prefix = "korda-rag-${var.environment}-ingestor-runtime-"
  policy      = data.aws_iam_policy_document.ingestor_runtime.json
  tags        = var.tags
}

data "aws_iam_policy_document" "external_secrets_runtime" {
  statement {
    sid = "ListSecrets"
    actions = [
      "secretsmanager:ListSecrets"
    ]
    resources = ["*"]
  }

  statement {
    sid = "ReadOnlyManagedSecrets"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = var.secrets_arns
  }

  statement {
    sid = "DecryptSecrets"
    actions = [
      "kms:Decrypt"
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_policy" "external_secrets_runtime" {
  name_prefix = "korda-rag-${var.environment}-external-secrets-"
  policy      = data.aws_iam_policy_document.external_secrets_runtime.json
  tags        = var.tags
}

module "rag_server_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.52"

  role_name = "korda-rag-${var.environment}-rag-server"

  role_policy_arns = {
    runtime = aws_iam_policy.rag_runtime.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = var.oidc_provider_arn
      namespace_service_accounts = ["${var.namespace}:rag-server"]
    }
  }

  tags = var.tags
}

module "ingestor_server_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.52"

  role_name = "korda-rag-${var.environment}-ingestor-server"

  role_policy_arns = {
    runtime = aws_iam_policy.ingestor_runtime.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = var.oidc_provider_arn
      namespace_service_accounts = ["${var.namespace}:ingestor-server"]
    }
  }

  tags = var.tags
}

module "external_secrets_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.52"

  role_name = "korda-rag-${var.environment}-external-secrets"

  role_policy_arns = {
    runtime = aws_iam_policy.external_secrets_runtime.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = var.oidc_provider_arn
      namespace_service_accounts = ["external-secrets:external-secrets"]
    }
  }

  tags = var.tags
}
