locals {
  bucket_prefix = "${var.bucket_name_prefix}-${var.environment}-${var.account_id}-${var.region}"
}

resource "aws_kms_key" "platform" {
  description             = "KMS key for KORDA RAG ${var.environment} platform encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "platform" {
  name          = "alias/korda-rag-${var.environment}"
  target_key_id = aws_kms_key.platform.key_id
}

resource "aws_s3_bucket" "audit" {
  bucket        = "${local.bucket_prefix}-audit"
  force_destroy = false
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.platform.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket" "backup" {
  bucket        = "${local.bucket_prefix}-backup"
  force_destroy = false
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.platform.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    id     = "retention"
    status = "Enabled"

    expiration {
      days = var.backup_retention_days
    }
  }
}

data "aws_iam_policy_document" "cloudtrail_s3" {
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.audit.arn]
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.audit.arn}/AWSLogs/${var.account_id}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = data.aws_iam_policy_document.cloudtrail_s3.json
}

resource "aws_cloudtrail" "audit" {
  count = var.enable_cloudtrail ? 1 : 0

  name                          = "korda-rag-${var.environment}-trail"
  s3_bucket_name                = aws_s3_bucket.audit.id
  include_global_service_events = true
  is_multi_region_trail         = false
  kms_key_id                    = aws_kms_key.platform.arn
  enable_logging                = true
  tags                          = var.tags
}

resource "aws_cloudwatch_log_group" "eks_audit" {
  name              = "/aws/eks/korda-rag-${var.environment}/audit"
  retention_in_days = var.eks_log_retention_days
  kms_key_id        = aws_kms_key.platform.arn
  tags              = var.tags
}
