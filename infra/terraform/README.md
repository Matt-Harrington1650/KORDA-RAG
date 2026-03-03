# KORDA RAG AWS Terraform Stack

This directory contains Terraform to provision the AWS foundation for a private, regulated-ready KORDA RAG deployment on EKS.

## Structure

- `modules/network`: VPC, subnets, NAT, DNS.
- `modules/governance`: KMS, CloudTrail, audit/backup S3, EKS audit log group.
- `modules/eks`: Private-endpoint EKS with CPU and GPU managed node groups.
- `modules/secrets`: AWS Secrets Manager placeholders (no secret values stored in Git).
- `modules/irsa`: IAM Roles for Service Accounts (RAG server, Ingestor, External Secrets).
- `envs/dev|stage|prod`: Environment stacks and per-env defaults.
- `scripts/plan.ps1`: Helper for init/plan/apply.

## Region and Residency

US-only is enforced through variable validation in each environment stack (`us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`).

## Usage

Example for `dev`:

```powershell
cd infra/terraform/envs/dev
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

## Notes

- Secrets are provisioned as empty Secrets Manager entries; values are injected out-of-band.
- Helm/Argo CD deployment consumes outputs from Terraform (cluster details, IRSA ARNs, secret names).
- Do not commit `backend.hcl`, `.tfstate`, or secret values.
