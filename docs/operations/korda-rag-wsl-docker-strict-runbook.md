# Run KORDA RAG Agent (WSL + Docker + NVIDIA Hosted + KORDA Strict)

This runbook starts KORDA RAG locally in WSL/Linux with Docker Compose and NVIDIA-hosted endpoints, with strict ingestion and post-ingest metadata enrichment enabled.

## What Must Be Done Before Startup

1. Verify runtime prerequisites:

```bash
docker --version
docker compose version
```

Required baseline:
- Docker Engine + Docker Compose plugin.
- WSL/Linux shell from repo root.
- At least 50 GB available disk.

2. Set API key and log in to `nvcr.io`:

```bash
export NGC_API_KEY="nvapi-..."
export NVIDIA_API_KEY="$NGC_API_KEY"
echo "${NGC_API_KEY}" | docker login nvcr.io -u '$oauthtoken' --password-stdin
```

3. Confirm required files exist:
- `deploy/compose/docker-compose-ingestor-server.yaml`
- `deploy/compose/docker-compose-rag-server.yaml`
- `deploy/compose/vectordb.yaml`
- `deploy/compose/docker-compose-ingestor-server.korda-strict.yaml`
- `src/nvidia_rag/rag_server/prompt-korda-epc.yaml`

## Startup Sequence

### Option A: One-command startup script

```bash
bash scripts/cloud/run-korda-rag-korda-strict.sh
```

### Option A2: PowerShell wrapper (launches via WSL)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\cloud\korda-rag-korda-strict.ps1 -Action start -NgcApiKey "nvapi-..."
```

### Option B: Manual commands

```bash
cd /mnt/c/code/KORDA-RAG
source deploy/compose/.env

export APP_EMBEDDINGS_SERVERURL="https://integrate.api.nvidia.com/v1"
export APP_LLM_SERVERURL=""
export APP_QUERYREWRITER_SERVERURL=""
export APP_FILTEREXPRESSIONGENERATOR_SERVERURL=""
export APP_RANKING_SERVERURL=""
export SUMMARY_LLM_SERVERURL=""

export OCR_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-ocr"
export OCR_INFER_PROTOCOL="http"
export YOLOX_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-page-elements-v3"
export YOLOX_INFER_PROTOCOL="http"
export YOLOX_GRAPHIC_ELEMENTS_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-graphic-elements-v1"
export YOLOX_GRAPHIC_ELEMENTS_INFER_PROTOCOL="http"
export YOLOX_TABLE_STRUCTURE_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-table-structure-v1"
export YOLOX_TABLE_STRUCTURE_INFER_PROTOCOL="http"

export APP_NVINGEST_CAPTIONENDPOINTURL="https://integrate.api.nvidia.com/v1/chat/completions"
export VLM_CAPTION_ENDPOINT="https://integrate.api.nvidia.com/v1/chat/completions"
export PROMPT_CONFIG_FILE="${PWD}/src/nvidia_rag/rag_server/prompt-korda-epc.yaml"

docker compose -f deploy/compose/vectordb.yaml up -d
docker compose \
  -f deploy/compose/docker-compose-ingestor-server.yaml \
  -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
  up -d
docker compose -f deploy/compose/docker-compose-rag-server.yaml up -d
```

## Verification and Smoke Tests

### Option A: One-command verify script

```bash
bash scripts/cloud/verify-korda-rag-korda-strict.sh
```

PowerShell wrapper equivalent:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\cloud\korda-rag-korda-strict.ps1 -Action verify -RagBaseUrl "http://localhost:8081/v1" -IngestorBaseUrl "http://localhost:8082/v1" -CollectionName "multimodal_data"
```

### Option B: Manual checks

1. Containers:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

2. Health:

```bash
curl -s "http://localhost:8082/v1/health?check_dependencies=true"
curl -s "http://localhost:8081/v1/health?check_dependencies=true"
```

3. Strict env in ingestor:

```bash
docker exec ingestor-server sh -lc 'printenv | egrep "PROMPT_CONFIG_FILE|INGESTION_JSON_STRICT_MODE|ENABLE_METADATA_ENRICHMENT|METADATA_EXTRACTION_MIN_SOURCE_QUALITY"'
```

4. Create collection:

```bash
curl -X POST "http://localhost:8082/v1/collection" \
  -H "Content-Type: application/json" \
  -d '{"collection_name":"multimodal_data","embedding_dimension":2048}'
```

5. Upload sample document:

```bash
UPLOAD_JSON='{"collection_name":"multimodal_data","blocking":true,"split_options":{"chunk_size":512,"chunk_overlap":150},"custom_metadata":[],"generate_summary":true}'

curl -X POST "http://localhost:8082/v1/documents" \
  -F "documents=@data/multimodal/multimodal_test.pdf;type=application/pdf" \
  -F "data=${UPLOAD_JSON};type=application/json"
```

6. Generate answer:

```bash
curl -X POST "http://localhost:8081/v1/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "messages":[{"role":"user","content":"Summarize key technical points from the uploaded document."}],
    "use_knowledge_base": true,
    "collection_names": ["multimodal_data"],
    "enable_citations": true,
    "enable_reranker": true,
    "reranker_top_k": 10,
    "vdb_top_k": 100
  }'
```

## Shutdown

### Option A: One-command shutdown script

```bash
bash scripts/cloud/shutdown-korda-rag-korda-strict.sh
```

PowerShell wrapper equivalent:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\cloud\korda-rag-korda-strict.ps1 -Action stop
```

Run full start+verify in one command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\cloud\korda-rag-korda-strict.ps1 -Action all -NgcApiKey "nvapi-..."
```

### Option B: Manual commands

```bash
docker compose -f deploy/compose/docker-compose-rag-server.yaml down
docker compose \
  -f deploy/compose/docker-compose-ingestor-server.yaml \
  -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
  down
docker compose -f deploy/compose/vectordb.yaml down
```

## Troubleshooting Checkpoints

1. If `ingestor` health fails with endpoint errors, re-check exported hosted endpoint variables in the same terminal used for `docker compose up`.
2. If strict mode does not appear active, verify `deploy/compose/docker-compose-ingestor-server.korda-strict.yaml` is included in the compose command.
3. If upload returns strict failures, inspect `validation_errors` and `failed_documents` fields in the response body.
4. If generation returns no citations, verify `collection_names`, `use_knowledge_base=true`, and successful ingestion status first.
5. If wrapper fails early, it usually indicates one of:
   - missing WSL distro,
   - Docker Desktop service not running (`com.docker.service`),
   - Docker CLI not available inside the selected distro (WSL integration disabled).
