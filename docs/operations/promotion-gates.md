# Promotion Gates (Dev -> Stage -> Prod)

## Dev -> Stage

- [ ] Integration test suite pass
- [ ] Security policy checks pass (Kyverno and network policies)
- [ ] Smoke API health checks pass
- [ ] Ingestion and retrieval regression pass

## Stage -> Prod

- [ ] Stage burn-in window complete (minimum 48 hours)
- [ ] Error budget consumption below threshold
- [ ] DR restore rehearsal pass
- [ ] Compliance evidence bundle reviewed
- [ ] Manual approval from platform owner + security owner

## Immutable Inputs

- Helm chart version pinned
- Overlay file hash pinned
- Container image tags pinned
- Terraform module/version references pinned
