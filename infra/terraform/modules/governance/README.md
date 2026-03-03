# Module: governance

Implements baseline regulated-ready controls:

- KMS key with rotation
- S3 audit bucket for CloudTrail
- S3 backup bucket with versioning and lifecycle
- CloudTrail trail (US-only region stack)
- CloudWatch log group for EKS audit logs

This module does not write any secret values.
