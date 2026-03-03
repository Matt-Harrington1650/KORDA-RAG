# KORDA RAG Housekeeping Checklist (Pre-Implementation)

Use this checklist before provisioning any cloud resources.

## 1. Product and Scope Freeze

- [ ] Confirm phase outcomes:
  - [ ] PoC: ingestion, citations, multimodal query, health checks, recovery drill.
  - [ ] Prod: SLOs, audited controls, tested backup/restore evidence.
- [ ] Confirm phase-1 in-scope APIs:
  - [ ] `POST /v1/generate`
  - [ ] `POST /v1/chat/completions`
  - [ ] `POST /v1/search`
  - [ ] `POST /v1/summary`
- [ ] Confirm phase-1 out-of-scope:
  - [ ] Active-active multi-region
  - [ ] Public endpoint exposure
  - [ ] Tenant isolation redesign

## 2. Security and Compliance Readiness

- [ ] Data classification matrix approved.
- [ ] Retention and deletion SLA approved.
- [ ] Secrets policy approved:
  - [ ] Only AWS Secrets Manager
  - [ ] No secret values in Git or Helm overlays
- [ ] Encryption policy approved:
  - [ ] KMS for EBS/S3/logging
- [ ] Audit policy approved:
  - [ ] CloudTrail enabled
  - [ ] EKS control plane audit logs retained
- [ ] Access policy approved:
  - [ ] IRSA role boundaries
  - [ ] Break-glass process

## 3. Operational Readiness

- [ ] SLOs and error budgets approved.
- [ ] On-call owner and escalation path documented.
- [ ] Incident runbooks prepared:
  - [ ] API outage
  - [ ] NVIDIA API rate limiting
  - [ ] Milvus degradation
  - [ ] Ingestion backlog
- [ ] Backup/restore policy approved:
  - [ ] Milvus data
  - [ ] Object storage
  - [ ] Config/state from Git

## 4. Architecture Freeze

- [ ] Environment overlays set: `dev`, `stage`, `prod`.
- [ ] Feature flag defaults set by env.
- [ ] Vector retrieval defaults set by env.
- [ ] Network model set to private-only.

## 5. Control Evidence Baseline

- [ ] Security control IDs mapped to implementation artifact.
- [ ] Evidence collection owners assigned.
- [ ] Quarterly control test cadence defined.
