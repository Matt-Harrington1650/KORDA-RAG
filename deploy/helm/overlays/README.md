# Helm Overlays for Cloud Environments

These overlays keep the base chart unchanged and apply environment-specific controls for:

- Private-only service exposure
- NVIDIA-hosted model endpoints
- Externalized secrets (no keys in Git)
- IRSA annotations for service accounts
- Environment feature flags and performance defaults

## Files

- `dev.yaml`
- `stage.yaml`
- `prod.yaml`

## Required substitutions before deploy

Set these placeholders from Terraform outputs:

- `<RAG_SERVER_IRSA_ROLE_ARN>`
- `<INGESTOR_SERVER_IRSA_ROLE_ARN>`
- `<EXTERNAL_SECRETS_ROLE_ARN>`

## Example render

```bash
helm template rag deploy/helm/nvidia-blueprint-rag \
  -n rag-dev \
  -f deploy/helm/overlays/dev.yaml
```
