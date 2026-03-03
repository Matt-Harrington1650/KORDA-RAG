# AWS EKS Implementation Guide (KORDA RAG)

This is the execution guide for the AWS + EKS + GitOps implementation in this repository.

## 0. Prerequisites

- AWS accounts and IAM access for `dev`, `stage`, `prod`
- Terraform `>=1.7`
- `kubectl`, `helm`, `argocd` CLI
- Private connectivity to cluster API endpoint
- A US AWS region (`us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`)

## 1. Provision Infrastructure

### 1.1 Configure environment backend

1. Copy `backend.hcl.example` to `backend.hcl`.
2. Set state bucket and lock table.

### 1.2 Run Terraform

Example (`dev`):

```powershell
cd infra/terraform/envs/dev
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

### 1.3 Capture required outputs

```powershell
terraform output irsa_role_arns
terraform output secret_names
terraform output cluster_name
```

## 2. Populate Secrets Manager

The Terraform stack creates secret entries only. Add values using secure process:

- `/korda-rag/<env>/ngc_api_key`
- `/korda-rag/<env>/llm_api_key`
- `/korda-rag/<env>/embeddings_api_key`
- `/korda-rag/<env>/ranking_api_key`
- `/korda-rag/<env>/query_rewriter_api_key`
- `/korda-rag/<env>/filter_expression_api_key`
- `/korda-rag/<env>/vlm_api_key`
- `/korda-rag/<env>/summary_llm_api_key`
- `/korda-rag/<env>/reflection_llm_api_key`

## 3. Patch GitOps Placeholders

Replace placeholders before sync:

- `<RAG_SERVER_IRSA_ROLE_ARN>`
- `<INGESTOR_SERVER_IRSA_ROLE_ARN>`
- `<EXTERNAL_SECRETS_ROLE_ARN>`

Files to patch:

- `deploy/helm/overlays/dev.yaml`
- `deploy/helm/overlays/stage.yaml`
- `deploy/helm/overlays/prod.yaml`
- `deploy/gitops/argocd/apps/dev/01-external-secrets.yaml`
- `deploy/gitops/argocd/apps/stage/01-external-secrets.yaml`
- `deploy/gitops/argocd/apps/prod/01-external-secrets.yaml`

Optional helper:

```powershell
.\scripts\cloud\patch-irsa-placeholders.ps1 `
  -Environment dev `
  -RagServerRoleArn arn:aws:iam::<acct>:role/korda-rag-dev-rag-server `
  -IngestorServerRoleArn arn:aws:iam::<acct>:role/korda-rag-dev-ingestor-server `
  -ExternalSecretsRoleArn arn:aws:iam::<acct>:role/korda-rag-dev-external-secrets
```

## 4. Bootstrap Argo CD

1. Apply project:

```bash
kubectl apply -f deploy/gitops/argocd/projects/korda-rag.yaml
```

2. Apply root app by environment:

```bash
kubectl apply -f deploy/gitops/argocd/apps/root-dev.yaml
kubectl apply -f deploy/gitops/argocd/apps/root-stage.yaml
kubectl apply -f deploy/gitops/argocd/apps/root-prod.yaml
```

## 5. Verify Deployment

### 5.1 External Secrets resolution

```bash
kubectl get externalsecret -n rag-dev
kubectl get secret ngc-api -n rag-dev
kubectl get secret ngc-secret -n rag-dev
kubectl get secret rag-api-keys -n rag-dev
```

### 5.2 RAG platform health

```bash
kubectl get pods -n rag-dev
kubectl port-forward -n rag-dev svc/rag-server 8081:8081
curl "http://localhost:8081/v1/health?check_dependencies=true"
```

### 5.3 Promotion smoke scripts

```powershell
.\scripts\cloud\verify-promotion-gate.ps1 -Namespace rag-dev
.\scripts\cloud\smoke-query.ps1 -CollectionName multimodal_data
```

## 6. Promotion Model

- `dev`: auto-sync enabled.
- `stage`: manual sync after integration tests pass.
- `prod`: manual sync with approval and evidence bundle.

## 7. Compliance Controls Mapped to Artifacts

- Encryption at rest: `infra/terraform/modules/governance`
- Audit trail: `infra/terraform/modules/governance`
- IRSA least privilege: `infra/terraform/modules/irsa`
- Private-only services: `deploy/helm/overlays/*.yaml` + Kyverno policy
- Secret externalization: `deploy/gitops/bootstrap/*-secrets`
