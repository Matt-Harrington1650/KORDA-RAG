# Dev/Stage/Prod One-Command Verification Checklist

Use this checklist with:

```powershell
.\scripts\cloud\verify-env-checklist.ps1 -Environment all
```

Or environment-specific:

```powershell
.\scripts\cloud\verify-env-checklist.ps1 -Environment dev
.\scripts\cloud\verify-env-checklist.ps1 -Environment stage
.\scripts\cloud\verify-env-checklist.ps1 -Environment prod
```

Skip strict fixture tests if your runtime does not have unit-test dependencies installed:

```powershell
.\scripts\cloud\verify-env-checklist.ps1 -Environment all -SkipStrictFixtureTests
```

## What this command verifies

1. Overlay controls are present in:
- `deploy/helm/overlays/dev.yaml`
- `deploy/helm/overlays/stage.yaml`
- `deploy/helm/overlays/prod.yaml`

Required controls:
- `PROMPT_CONFIG_FILE: "/prompt-korda-epc.yaml"`
- `INGESTION_JSON_STRICT_MODE: "True"`
- `INGESTION_CAPTION_MIN_CONFIDENCE: "0.80"`
- `INGESTION_SUMMARY_MIN_CONFIDENCE: "0.85"`
- `INGESTION_CAPTION_MIN_CONFIDENCE_BY_ARTIFACT: "<json map>"`
- `INGESTION_SUMMARY_MIN_CONFIDENCE_BY_DOCUMENT_TYPE: "<json map>"`
- `INGESTION_FAIL_ON_MISSING_CRITICAL: "True"`
- `ENABLE_METADATA_ENRICHMENT: "False|True"` (must be `True` in `stage`/`prod`)
- `METADATA_EXTRACTION_MIN_SOURCE_QUALITY: "0.xx"`
- `strictObservability.enabled: true|false` (must be `true` in `stage`/`prod`)

2. Runtime promotion-gate checks:
- `scripts/cloud/verify-promotion-gate.ps1`

Checks include:
- Pods running in target namespace
- Required secrets present
- RAG and Ingestor dependency health endpoints

3. Query/generation smoke:
- `scripts/cloud/smoke-query.ps1`

4. Strict fixture smoke tests:
- `tests/unit/test_ingestor_server/test_strict_ingestion_api_smoke.py`
- `tests/unit/test_utils/test_ingestion_validation.py`
- `tests/unit/test_utils/test_metadata_enrichment.py`

## Promotion mapping

- `dev` verification maps to `Dev -> Stage` gate readiness.
- `stage` verification maps to `Stage -> Prod` gate readiness.
- `prod` verification maps to post-promotion runtime validation.

## Notes

- This command does not replace required manual approvals or compliance evidence review.
- Strict fixture smoke tests require Python test dependencies (`pytest`, `fastapi`, and unit-test requirements).
- Stage/Prod observability artifacts:
  - `deploy/config/korda-strict-ingestion-dashboard.json`
  - `deploy/config/korda-strict-validation-alerts.yaml`
- Calibration artifact and script:
  - `docs/operations/calibration-threshold-recommendations.json`
  - `scripts/cloud/calibrate-ingestion-thresholds.py`
- CI workflow for strict tests + calibration:
  - `.github/workflows/strict-ingestion-ci.yml`
  - `docs/operations/strict-ingestion-ci.md`
- Use alongside:
  - `docs/operations/promotion-gates.md`
  - `docs/cloud/aws-eks-implementation.md`
