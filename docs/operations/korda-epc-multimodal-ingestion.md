# KORDA EPC Multimodal Ingestion (Strict JSON)

This repository now includes a fail-closed prompt + validator path for EPC multimodal ingestion.

## What was added

1. Prompt pack files:
- `src/nvidia_rag/rag_server/prompt-korda-epc.yaml`
- `deploy/helm/nvidia-blueprint-rag/files/prompt-korda-epc.yaml`

2. Strict ingestion contracts and rule validators:
- `src/nvidia_rag/utils/ingestion_validation.py`
- `CaptionRecordV1`
- `SummaryRecordV1`
- `MetadataRecordV1`

3. Ingestion/summarization enforcement hooks:
- Caption validation in `src/nvidia_rag/ingestor_server/main.py`
- Summary validation in `src/nvidia_rag/utils/summarization.py`
4. Post-ingest metadata enrichment worker:
- Worker implementation: `src/nvidia_rag/utils/metadata_enrichment.py`
- Pipeline wiring: `src/nvidia_rag/ingestor_server/main.py`
- Prompt key used: `metadata_extraction_prompt`

5. Mixed EPC metadata schema template:
- `deploy/config/korda-epc-metadata-schema.json`

6. Helm wiring for prompt selection:
- ConfigMap now includes `prompt-korda-epc.yaml`
- RAG + ingestor deployments mount:
  - `/prompt.yaml`
  - `/prompt-korda-epc.yaml`

## Runtime controls

Set these on ingestor server:

- `PROMPT_CONFIG_FILE=/prompt-korda-epc.yaml`
- `INGESTION_JSON_STRICT_MODE=true`
- `INGESTION_CAPTION_MIN_CONFIDENCE=0.80`
- `INGESTION_SUMMARY_MIN_CONFIDENCE=0.85`
- `INGESTION_CAPTION_MIN_CONFIDENCE_BY_ARTIFACT={"drawing":0.90,...}`
- `INGESTION_SUMMARY_MIN_CONFIDENCE_BY_DOCUMENT_TYPE={"drawing":0.90,...}`
- `INGESTION_FAIL_ON_MISSING_CRITICAL=true`
- `ENABLE_METADATA_ENRICHMENT=true`
- `METADATA_EXTRACTION_MIN_SOURCE_QUALITY=0.80` (recommended stage/prod baseline)

## Failure surfaces (non-breaking)

- Caption strict-validation failures are emitted via existing:
  - `validation_errors`
  - `failed_documents`
- Summary strict-validation failures are emitted via existing summary status path:
  - `FAILED` status in Redis/minio-backed summary status flow
- Metadata enrichment strict-validation failures are emitted via existing:
  - `validation_errors`
  - `failed_documents` (when strict mode + fail-closed are enabled)

## Notes

- API contracts remain unchanged:
  - `POST /v1/documents`
  - `GET /v1/status`
- Existing prompt merge behavior is unchanged:
  - default prompt file + override from `PROMPT_CONFIG_FILE`
- For local WSL/docker execution sequence with strict profile:
  - `docs/operations/korda-rag-wsl-docker-strict-runbook.md`
