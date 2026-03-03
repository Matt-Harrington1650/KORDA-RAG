# Module: irsa

Creates IAM Roles for Service Accounts:

- `rag-server`
- `ingestor-server`
- `external-secrets`

Policies grant least-privilege access to:

- specific Secrets Manager ARNs
- KMS decrypt for the platform CMK
- backup bucket read/write for ingestion workflows
