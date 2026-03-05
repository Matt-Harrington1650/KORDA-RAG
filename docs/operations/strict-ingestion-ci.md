# Strict Ingestion CI Workflow

This repository includes a dedicated workflow:

- `.github/workflows/strict-ingestion-ci.yml`

The workflow is designed to satisfy strict-ingestion validation requirements in a dependency-complete CI environment.

## What it runs

1. Python 3.12 setup (compatible with `requires-python >=3.11,<3.14`).
2. Strict-ingestion unit tests:
   - `tests/unit/test_ingestor_server/test_strict_ingestion_api_smoke.py`
   - `tests/unit/test_ingestor_server/test_ingestor_caption_validation.py`
   - `tests/unit/test_utils/test_ingestion_validation.py`
   - `tests/unit/test_utils/test_metadata_enrichment.py`
   - `tests/unit/test_utils/test_summarization.py`
   - `tests/unit/test_utils/test_configuration.py`
   - `tests/unit/test_observability/test_otel_metrics.py`
3. Corpus calibration command:
   - `scripts/cloud/calibrate-ingestion-thresholds.py`
4. Uploads calibration report artifact:
   - `docs/operations/calibration-threshold-recommendations.ci.json`

## Package index and proxy compatibility

The workflow supports private package mirrors through optional secrets:

- `PIP_INDEX_URL`
- `PIP_EXTRA_INDEX_URL`
- `PIP_TRUSTED_HOST`

If these are not set, the default pip index behavior is used.

## Manual cluster verification mode

`workflow_dispatch` supports an optional job for runtime environment checks:

- Installs `kubectl` and `helm`.
- Decodes kubeconfig from `KORDA_KUBECONFIG_B64`.
- Runs:
  - `scripts/cloud/verify-env-checklist.ps1`

Required secret:

- `KORDA_KUBECONFIG_B64` (base64-encoded kubeconfig content)

Manual inputs:

1. `run_cluster_verify` (`true|false`)
2. `target_environment` (`dev|stage|prod|all`)
3. `rag_base_url`
4. `ingestor_base_url`
5. `collection_name`
6. `skip_strict_fixture_tests` (`true|false`)

## Local equivalent commands

```bash
python -m pip install -e .[all]
python -m pip install -r tests/unit/requirements-test.txt
python -m pytest -v -s \
  tests/unit/test_ingestor_server/test_strict_ingestion_api_smoke.py \
  tests/unit/test_ingestor_server/test_ingestor_caption_validation.py \
  tests/unit/test_utils/test_ingestion_validation.py \
  tests/unit/test_utils/test_metadata_enrichment.py \
  tests/unit/test_utils/test_summarization.py \
  tests/unit/test_utils/test_configuration.py \
  tests/unit/test_observability/test_otel_metrics.py
python scripts/cloud/calibrate-ingestion-thresholds.py \
  --input-jsonl docs/operations/sample-corpus-calibration.jsonl \
  --output-json docs/operations/calibration-threshold-recommendations.ci.json \
  --target-precision 0.95 \
  --min-samples 20
```
