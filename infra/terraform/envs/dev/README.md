# Terraform Environment: dev

## Goals

- Fast feedback environment for integration and security policy validation.
- Private-only endpoint model.
- Cost-optimized NAT and node sizing.

## Apply

```powershell
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

## Required Post-Apply Steps

1. Populate Secrets Manager values created by the `secrets` module.
2. Export IRSA role ARNs and patch GitOps env manifests.
3. Bootstrap Argo CD root app for `dev`.
