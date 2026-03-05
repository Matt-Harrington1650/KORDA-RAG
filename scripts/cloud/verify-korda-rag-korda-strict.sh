#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

require_cmd() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "Missing required command: ${name}" >&2
    exit 1
  fi
}

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "Missing required file: ${path}" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd curl

require_file "data/multimodal/multimodal_test.pdf"

RAG_BASE_URL="${RAG_BASE_URL:-http://localhost:8081/v1}"
INGESTOR_BASE_URL="${INGESTOR_BASE_URL:-http://localhost:8082/v1}"
COLLECTION_NAME="${COLLECTION_NAME:-multimodal_data}"

echo "Container status:"
docker ps --format "table {{.Names}}\t{{.Status}}"

echo
echo "Ingestor health:"
curl -sS "${INGESTOR_BASE_URL}/health?check_dependencies=true"
echo
echo
echo "RAG health:"
curl -sS "${RAG_BASE_URL}/health?check_dependencies=true"
echo
echo
echo "Strict environment check in ingestor container:"
docker exec ingestor-server sh -lc 'printenv | egrep "PROMPT_CONFIG_FILE|INGESTION_JSON_STRICT_MODE|ENABLE_METADATA_ENRICHMENT|METADATA_EXTRACTION_MIN_SOURCE_QUALITY"'
echo

echo "Creating collection ${COLLECTION_NAME}..."
create_collection_response="$(curl -sS -X POST "${INGESTOR_BASE_URL}/collection" \
  -H "Content-Type: application/json" \
  -d "{\"collection_name\":\"${COLLECTION_NAME}\",\"embedding_dimension\":2048}")"
echo "${create_collection_response}"
echo

echo "Uploading sample document in blocking mode..."
UPLOAD_JSON="{\"collection_name\":\"${COLLECTION_NAME}\",\"blocking\":true,\"split_options\":{\"chunk_size\":512,\"chunk_overlap\":150},\"custom_metadata\":[],\"generate_summary\":true}"
upload_response="$(curl -sS -X POST "${INGESTOR_BASE_URL}/documents" \
  -F "documents=@data/multimodal/multimodal_test.pdf;type=application/pdf" \
  -F "data=${UPLOAD_JSON};type=application/json")"
echo "${upload_response}"
echo

echo "Generating response from RAG endpoint..."
generate_response="$(curl -sS -X POST "${RAG_BASE_URL}/generate" \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\":[{\"role\":\"user\",\"content\":\"Summarize key technical points from the uploaded document.\"}],
    \"use_knowledge_base\": true,
    \"collection_names\": [\"${COLLECTION_NAME}\"],
    \"enable_citations\": true,
    \"enable_reranker\": true,
    \"reranker_top_k\": 10,
    \"vdb_top_k\": 100
  }")"
echo "${generate_response}"
echo

echo "Verification and smoke flow completed."
