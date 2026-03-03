# Terraform Environment: prod

## Goals

- Production environment for pilot-to-scaled rollout.
- Private-only endpoint model.
- High-availability networking and larger node group bounds.

## Apply

```powershell
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

## Required Post-Apply Steps

1. Populate Secrets Manager values created by the `secrets` module.
2. Export IRSA role ARNs and patch GitOps env manifests.
3. Bootstrap Argo CD root app for `prod`.
