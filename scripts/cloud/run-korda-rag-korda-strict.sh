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

echo "Docker version:"
docker --version
echo "Docker Compose version:"
docker compose version

require_file "deploy/compose/docker-compose-ingestor-server.yaml"
require_file "deploy/compose/docker-compose-ingestor-server.korda-strict.yaml"
require_file "deploy/compose/docker-compose-rag-server.yaml"
require_file "deploy/compose/vectordb.yaml"
require_file "src/nvidia_rag/rag_server/prompt-korda-epc.yaml"

if [[ -z "${NGC_API_KEY:-}" ]]; then
  echo "NGC_API_KEY is not set. Export it before running this script." >&2
  exit 1
fi

export NVIDIA_API_KEY="${NVIDIA_API_KEY:-${NGC_API_KEY}}"

# shellcheck source=/dev/null
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

export PROMPT_CONFIG_FILE="${ROOT_DIR}/src/nvidia_rag/rag_server/prompt-korda-epc.yaml"

echo "Starting vector database dependencies..."
docker compose -f deploy/compose/vectordb.yaml up -d

echo "Starting ingestor stack with strict profile overlay..."
docker compose \
  -f deploy/compose/docker-compose-ingestor-server.yaml \
  -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
  up -d

echo "Starting RAG server and frontend..."
docker compose -f deploy/compose/docker-compose-rag-server.yaml up -d

echo "Startup complete. Run scripts/cloud/verify-korda-rag-korda-strict.sh for health + smoke checks."
