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

## One-Command Verification

Run this command to verify overlays + runtime gates for `dev`, `stage`, and `prod`:

```powershell
.\scripts\cloud\verify-env-checklist.ps1 -Environment all
```

Environment-specific runs:

```powershell
.\scripts\cloud\verify-env-checklist.ps1 -Environment dev
.\scripts\cloud\verify-env-checklist.ps1 -Environment stage
.\scripts\cloud\verify-env-checklist.ps1 -Environment prod
```

This command validates:

- Environment overlay strict-ingestion controls:
  - `PROMPT_CONFIG_FILE=/prompt-korda-epc.yaml`
  - `INGESTION_JSON_STRICT_MODE=True`
  - global + per-class confidence thresholds and fail-closed flag
  - metadata enrichment enablement and quality threshold
- Existing promotion-gate runtime checks in `verify-promotion-gate.ps1`
- Search/generate smoke path in `smoke-query.ps1`
- Strict fixture API smoke tests:
  - `tests/unit/test_ingestor_server/test_strict_ingestion_api_smoke.py`
  - `tests/unit/test_utils/test_ingestion_validation.py`
  - `tests/unit/test_utils/test_metadata_enrichment.py`

## CI Automation

- Dedicated workflow:
  - `.github/workflows/strict-ingestion-ci.yml`
- CI runbook:
  - `docs/operations/strict-ingestion-ci.md`

## Stage/Prod KPI and Alerts

- Dashboard JSON:
  - `deploy/config/korda-strict-ingestion-dashboard.json`
- Alert rules:
  - `deploy/config/korda-strict-validation-alerts.yaml`
- Runbook:
  - `docs/operations/strict-ingestion-observability.md`

## Threshold Calibration

- Calibration script:
  - `scripts/cloud/calibrate-ingestion-thresholds.py`
- Calibration runbook:
  - `docs/operations/threshold-calibration.md`
