# Terraform Environment: stage

## Goals

- Pre-production validation with production-like controls.
- Private-only endpoint model.
- Full integration, security, and DR rehearsal.

## Apply

```powershell
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

## Required Post-Apply Steps

1. Populate Secrets Manager values created by the `secrets` module.
2. Export IRSA role ARNs and patch GitOps env manifests.
3. Bootstrap Argo CD root app for `stage`.
