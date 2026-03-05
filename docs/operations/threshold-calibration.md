# Threshold Calibration (Strict Ingestion)

Use the calibration script to tune strict confidence thresholds by document class.

## Script

- `scripts/cloud/calibrate-ingestion-thresholds.py`

## Input format

Provide a JSONL file with per-document class labels and confidence outcomes.

Example line:

```json
{"document_class":"drawing","caption":{"confidence":0.91,"is_correct":true},"summary":{"confidence":0.88,"is_correct":true}}
```

Supported keys:
- `document_class` (or `doc_class`, `artifact_type`, `document_type`)
- `caption.confidence`, `caption.is_correct`
- `summary.confidence`, `summary.is_correct`

## Run

```bash
python scripts/cloud/calibrate-ingestion-thresholds.py \
  --input-jsonl docs/operations/sample-corpus-calibration.jsonl \
  --output-json docs/operations/calibration-threshold-recommendations.json \
  --target-precision 0.95 \
  --min-samples 20
```

## Output

The report contains:
- `caption_thresholds` by class
- `summary_thresholds` by class
- estimated precision/recall/support at each recommended threshold

## Promotion usage

1. Run calibration on stage corpus replay labels.
2. Review classes marked `target_not_met` or `insufficient_samples`.
3. Update stage/prod threshold policy env vars:
   - `INGESTION_CAPTION_MIN_CONFIDENCE_BY_ARTIFACT`
   - `INGESTION_SUMMARY_MIN_CONFIDENCE_BY_DOCUMENT_TYPE`
4. Re-run promotion verification and monitor strict-failure KPIs after rollout.
