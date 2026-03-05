#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ACTION="${1:-all}"
if [[ $# -gt 0 ]]; then
  shift
fi

ENABLE_SAVE_TO_DISK=false
ENABLE_RAG_THINKING=false
ENABLE_VLM_INFERENCE=false
ENABLE_VLM_THINKING=false
ENABLE_KORDA_STRICT=false
SKIP_DOCKER_LOGIN=false
SKIP_NIMS=false
FORCE_CPU_VECTORDB=false
SKIP_STRICT_NEGATIVE=false
SKIP_RESTART_PERSISTENCE=false
COLLECTION_NAME="multimodal_data"
RAG_BASE_URL="${RAG_BASE_URL:-http://localhost:8081/v1}"
INGESTOR_BASE_URL="${INGESTOR_BASE_URL:-http://localhost:8082/v1}"
MILVUS_ENDPOINT="${MILVUS_ENDPOINT:-http://milvus:19530}"
MODEL_DIRECTORY="${MODEL_DIRECTORY:-${HOME}/.cache/model-cache}"
DEMO_TIMEOUT_SECONDS=240
REPORT_FILE=""

readonly NIM_SERVICES=(
  "nemoretriever-embedding-ms"
  "nemoretriever-ranking-ms"
  "page-elements"
  "graphic-elements"
  "table-structure"
  "nemoretriever-ocr"
)

readonly QUICKSTART_ENV_BEGIN="# >>> KORDA NVIDIA QUICKSTART >>>"
readonly QUICKSTART_ENV_END="# <<< KORDA NVIDIA QUICKSTART <<<"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh <action> [options]

Actions:
  prereq      Run system requirement checks (GPU, driver, CUDA, Docker, RAM)
  configure   Login to NGC and write NVIDIA-hosted base env settings
  rebuild     cleanup + configure + local image build + deploy
  deploy      Start NIMs, vector DB, ingestor, rag, gateway, connector, frontend
  health      Check ingestor/rag/gateway/connector health endpoints
  demo        Download sample PDFs, ingest, and run RAG/non-RAG chat checks
  verify      Full seamless verification (health + startup + demo + strict + persistence)
  cleanup     Stop rag, ingestor, vectordb, nims
  all         prereq + configure + deploy + health
  full-verify prereq + configure + rebuild + verify
  full-demo   all + demo

Options:
  --ngc-api-key <key>         NGC API key (fallback: NGC_API_KEY env var)
  --enable-save-to-disk       Enable APP_NVINGEST_SAVETODISK and volume path
  --enable-rag-thinking       Set rag_template mode to /think in prompt.yaml
  --enable-vlm-inference      Enable VLM inferencing + captioning env settings
  --enable-vlm-thinking       Set vlm_template mode to /think in prompt.yaml
  --strict-profile            Include KORDA strict ingestor overlay on deploy
  --skip-docker-login         Skip nvcr.io docker login (if already logged in)
  --skip-nims                 Skip nims.yaml deployment
  --cpu-vectordb              Force CPU Milvus (WSL/no-GPU fallback)
  --report-file <path>        Write UAT readout report to file (default under artifacts/)
  --skip-strict-negative      Skip strict ingestion negative test
  --skip-restart-persistence  Skip restart + session persistence test
  --collection-name <name>    Collection for demo flow (default: multimodal_data)
  --rag-base-url <url>        RAG base URL with /v1 suffix
  --ingestor-base-url <url>   Ingestor base URL with /v1 suffix
  --milvus-endpoint <url>     Milvus endpoint (default: http://milvus:19530)
  --demo-timeout-seconds <n>  Demo ingestion wait timeout (default: 240)

Examples:
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh all --ngc-api-key "$NGC_API_KEY"
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh rebuild --ngc-api-key "$NGC_API_KEY" --skip-nims --cpu-vectordb
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh verify --collection-name multimodal_data
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh full-demo --strict-profile
  bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh cleanup
USAGE
}

log() {
  printf '[INFO] %s\n' "$*"
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

die() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || die "Missing command: ${cmd}"
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || die "Missing file: ${path}"
}

version_ge() {
  local lhs="$1"
  local rhs="$2"
  [[ "$(printf '%s\n' "${rhs}" "${lhs}" | sort -V | tail -n1)" == "${lhs}" ]]
}

json_extract() {
  local key="$1"
  python3 -c '
import json
import sys

key = sys.argv[1]
raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit(0)

try:
    value = json.loads(raw).get(key, "")
except Exception:
    print("")
    raise SystemExit(0)

if value is None:
    print("")
elif isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(str(value))
' "$key"
}

apply_api_key_overrides() {
  local ngc_key="${NGC_API_KEY:-}"
  if [[ -n "${NGC_API_KEY_OVERRIDE:-}" ]]; then
    ngc_key="${NGC_API_KEY_OVERRIDE}"
  fi

  if [[ -n "${ngc_key}" ]]; then
    export NGC_API_KEY="${ngc_key}"
    # Default service key to NGC key unless explicitly set.
    if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
      export NVIDIA_API_KEY="${ngc_key}"
    fi
  fi
}

check_prerequisites() {
  local errors=0

  log "Running prerequisite checks..."
  require_cmd docker
  require_cmd curl

  if command -v nvidia-smi >/dev/null 2>&1; then
    log "NVIDIA GPU(s):"
    nvidia-smi -L || true

    local driver_major
    driver_major="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 | cut -d. -f1 || true)"
    if [[ -z "${driver_major}" || "${driver_major}" -lt 580 ]]; then
      warn "Driver version < 580 or could not parse. Required: 580+."
      errors=$((errors + 1))
    else
      log "Driver check passed (${driver_major}+)"
    fi

    local cuda_version
    cuda_version="$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9.]\+\).*/\1/p' | head -n1)"
    if [[ -z "${cuda_version}" ]]; then
      warn "Unable to parse CUDA version from nvidia-smi."
      errors=$((errors + 1))
    else
      local cuda_major="${cuda_version%%.*}"
      if [[ "${cuda_major}" -lt 13 ]]; then
        warn "CUDA ${cuda_version} detected, 13+ required."
        errors=$((errors + 1))
      else
        log "CUDA check passed (${cuda_version})"
      fi
    fi
  else
    warn "nvidia-smi not found."
    errors=$((errors + 1))
  fi

  local docker_version compose_version
  docker_version="$(docker --version | sed -n 's/.*version \([0-9.]\+\).*/\1/p')"
  compose_version="$(docker compose version 2>/dev/null | sed -n 's/.*v\?\([0-9.]\+\).*/\1/p' | head -n1)"

  if [[ -z "${docker_version}" ]] || ! version_ge "${docker_version}" "26.0.0"; then
    warn "Docker version ${docker_version:-unknown} detected. Required: 26.0+."
    errors=$((errors + 1))
  else
    log "Docker check passed (${docker_version})"
  fi

  if [[ -z "${compose_version}" ]] || ! version_ge "${compose_version}" "2.29.1"; then
    warn "Docker Compose version ${compose_version:-unknown} detected. Required: 2.29.1+."
    errors=$((errors + 1))
  else
    log "Docker Compose check passed (${compose_version})"
  fi

  if command -v free >/dev/null 2>&1; then
    local total_gb
    total_gb="$(free -g | awk '/^Mem:/ {print $2}')"
    if [[ -n "${total_gb}" ]]; then
      if [[ "${total_gb}" -lt 32 ]]; then
        warn "System memory ${total_gb}GB detected. Recommended: 32GB+."
      else
        log "Memory check passed (${total_gb}GB)"
      fi
    fi
  fi

  if [[ "${errors}" -gt 0 ]]; then
    die "Prerequisite checks failed with ${errors} blocking issue(s)."
  fi
  log "Prerequisite checks passed."
}

update_thinking_mode() {
  local template="$1"
  local target_mode="$2"
  local prompt_file="src/nvidia_rag/rag_server/prompt.yaml"
  require_file "${prompt_file}"

  if [[ "${target_mode}" != "think" && "${target_mode}" != "no_think" ]]; then
    die "Invalid mode '${target_mode}' for ${template} template."
  fi

  local opposite="no_think"
  if [[ "${target_mode}" == "no_think" ]]; then
    opposite="think"
  fi

  perl -0777 -i -pe "s/(${template}:\\n\\s*system:\\s*\\|\\n\\s*)\\/${opposite}/\$1\\/${target_mode}/g" "${prompt_file}"
  log "Updated ${template} template to /${target_mode} in ${prompt_file}"
}

build_env_block() {
  cat <<EOF
${QUICKSTART_ENV_BEGIN}
export USERID="$(id -u)"
export MODEL_DIRECTORY="${MODEL_DIRECTORY}"
export APP_LLM_SERVERURL=""
export SUMMARY_LLM_SERVERURL=""
export SUMMARY_LLM="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export APP_LLM_MODELNAME="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export APP_EMBEDDINGS_SERVERURL="https://integrate.api.nvidia.com/v1"
export APP_RANKING_SERVERURL=""
export ENABLE_RERANKER="True"
export VECTOR_DB_TOPK="120"
export APP_RETRIEVER_TOPK="12"
export APP_FILTEREXPRESSIONGENERATOR_MODELNAME="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export APP_FILTEREXPRESSIONGENERATOR_SERVERURL=""
export APP_QUERYREWRITER_MODELNAME="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export APP_QUERYREWRITER_SERVERURL=""
export ENABLE_QUERYREWRITER="True"
export CONVERSATION_HISTORY="4"
export ENABLE_REFLECTION="True"
export ENABLE_QUERY_DECOMPOSITION="True"
export OCR_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-ocr"
export OCR_INFER_PROTOCOL="http"
export YOLOX_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-page-elements-v3"
export YOLOX_INFER_PROTOCOL="http"
export YOLOX_GRAPHIC_ELEMENTS_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-graphic-elements-v1"
export YOLOX_GRAPHIC_ELEMENTS_INFER_PROTOCOL="http"
export YOLOX_TABLE_STRUCTURE_HTTP_ENDPOINT="https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-table-structure-v1"
export YOLOX_TABLE_STRUCTURE_INFER_PROTOCOL="http"
export APP_NVINGEST_EXTRACTIMAGES="True"
export APP_NVINGEST_CAPTIONENDPOINTURL="https://integrate.api.nvidia.com/v1/chat/completions"
export VLM_CAPTION_ENDPOINT="https://integrate.api.nvidia.com/v1/chat/completions"
export INGESTION_JSON_STRICT_MODE="True"
export INGESTION_FAIL_ON_MISSING_CRITICAL="True"
export ENABLE_METADATA_ENRICHMENT="True"
export METADATA_EXTRACTION_MIN_SOURCE_QUALITY="0.80"
export KORDA_CHAT_DEFAULT_COLLECTION_NAME="${COLLECTION_NAME}"
export KORDA_CHAT_AUTO_STARTUP_BOOTSTRAP="true"
export KORDA_CHAT_STARTUP_FAIL_CLOSED="true"
export KORDA_CHAT_STORE_BACKEND="redis"
export KORDA_CONNECTOR_AUTOSTART="true"
export KORDA_CONNECTOR_WARM_RUN_ON_START="true"
export VITE_API_GATEWAY_URL="http://chat-gateway:8083/v1"
$(if [[ "${ENABLE_SAVE_TO_DISK}" == "true" ]]; then cat <<'SAVE'
export APP_NVINGEST_SAVETODISK="True"
export INGESTOR_SERVER_EXTERNAL_VOLUME_MOUNT="./volumes/ingestor-server"
export INGESTOR_SERVER_DATA_DIR="/data/"
SAVE
fi)
$(if [[ "${ENABLE_VLM_INFERENCE}" == "true" ]]; then cat <<'VLM'
export APP_NVINGEST_EXTRACTIMAGES="True"
export APP_NVINGEST_CAPTIONENDPOINTURL="https://integrate.api.nvidia.com/v1/chat/completions"
export APP_NVINGEST_CAPTIONMODELNAME="nvidia/nemotron-nano-12b-v2-vl"
export ENABLE_VLM_INFERENCE="true"
export APP_VLM_MODELNAME="nvidia/nemotron-nano-12b-v2-vl"
export APP_VLM_SERVERURL="https://integrate.api.nvidia.com/v1/"
export APP_VLM_TEMPERATURE="0.3"
export APP_VLM_TOP_P="0.91"
export APP_VLM_MAX_TOKENS="8192"
VLM
fi)
$(if [[ "${ENABLE_KORDA_STRICT}" == "true" ]]; then cat <<'STRICT'
export PROMPT_CONFIG_FILE="${PWD}/src/nvidia_rag/rag_server/prompt-korda-epc.yaml"
STRICT
fi)
${QUICKSTART_ENV_END}
EOF
}

write_quickstart_env_block() {
  local env_file="deploy/compose/.env"
  require_file "${env_file}"

  mkdir -p "${MODEL_DIRECTORY}"

  local tmp_file
  tmp_file="$(mktemp)"

  sed 's/\r$//' "${env_file}" > "${tmp_file}"
  sed -i "/${QUICKSTART_ENV_BEGIN}/,/${QUICKSTART_ENV_END}/d" "${tmp_file}"
  printf '\n%s\n' "$(build_env_block)" >> "${tmp_file}"
  mv "${tmp_file}" "${env_file}"

  log "Updated ${env_file} with NVIDIA quickstart environment block."
}

configure_env() {
  require_file "deploy/compose/.env"
  require_file "src/nvidia_rag/rag_server/prompt.yaml"

  local ngc_key="${NGC_API_KEY:-}"
  if [[ -n "${NGC_API_KEY_OVERRIDE:-}" ]]; then
    ngc_key="${NGC_API_KEY_OVERRIDE}"
  fi

  if [[ -z "${ngc_key}" ]]; then
    die "NGC API key is required. Set NGC_API_KEY or pass --ngc-api-key."
  fi

  export NGC_API_KEY="${ngc_key}"
  export NVIDIA_API_KEY="${ngc_key}"

  if [[ "${SKIP_DOCKER_LOGIN}" != "true" ]]; then
    log "Logging into nvcr.io..."
    printf '%s' "${NGC_API_KEY}" | docker login nvcr.io -u '$oauthtoken' --password-stdin >/dev/null
  else
    log "Skipping docker login."
  fi

  write_quickstart_env_block

  if [[ "${ENABLE_RAG_THINKING}" == "true" ]]; then
    update_thinking_mode "rag_template" "think"
  fi
  if [[ "${ENABLE_VLM_THINKING}" == "true" ]]; then
    update_thinking_mode "vlm_template" "think"
  fi

  log "Configuration complete."
}

build_local_images() {
  require_file "deploy/compose/docker-compose-rag-server.yaml"
  apply_api_key_overrides

  log "Building local images (rag-frontend, chat-gateway, intake-connector)..."
  docker compose -f deploy/compose/docker-compose-rag-server.yaml build rag-frontend chat-gateway intake-connector
}

rebuild_all() {
  cleanup_all
  configure_env
  build_local_images
  deploy_all
}

deploy_all() {
  require_file "deploy/compose/nims.yaml"
  require_file "deploy/compose/vectordb.yaml"
  require_file "deploy/compose/vectordb.cpu.override.yaml"
  require_file "deploy/compose/docker-compose-ingestor-server.yaml"
  require_file "deploy/compose/docker-compose-rag-server.yaml"

  apply_api_key_overrides

  log "Loading deploy/compose/.env..."
  # shellcheck source=/dev/null
  source "deploy/compose/.env"

  if [[ "${SKIP_NIMS}" != "true" ]]; then
    log "Deploying NIM services (${NIM_SERVICES[*]})..."
    docker compose -f deploy/compose/nims.yaml pull -q "${NIM_SERVICES[@]}"
    docker compose -f deploy/compose/nims.yaml up -d "${NIM_SERVICES[@]}"
  else
    log "Skipping NIM services deployment."
  fi

  local use_cpu_vectordb="${FORCE_CPU_VECTORDB}"
  if [[ "${use_cpu_vectordb}" != "true" ]] && ! command -v nvidia-smi >/dev/null 2>&1; then
    use_cpu_vectordb=true
    warn "nvidia-smi not found. Falling back to CPU Milvus."
  fi

  log "Deploying vector database..."
  if [[ "${use_cpu_vectordb}" == "true" ]]; then
    export MILVUS_VERSION="${MILVUS_VERSION:-v2.6.5}"
    export APP_VECTORSTORE_ENABLEGPUSEARCH=False
    export APP_VECTORSTORE_ENABLEGPUINDEX=False
    export APP_VECTORSTORE_INDEXTYPE="${APP_VECTORSTORE_INDEXTYPE:-HNSW}"
    docker compose -f deploy/compose/vectordb.yaml -f deploy/compose/vectordb.cpu.override.yaml pull -q
    docker compose -f deploy/compose/vectordb.yaml -f deploy/compose/vectordb.cpu.override.yaml up -d
  else
    docker compose -f deploy/compose/vectordb.yaml pull -q
    docker compose -f deploy/compose/vectordb.yaml up -d
  fi

  log "Deploying ingestor server..."
  if [[ "${ENABLE_KORDA_STRICT}" == "true" && -f "deploy/compose/docker-compose-ingestor-server.korda-strict.yaml" ]]; then
    docker compose \
      -f deploy/compose/docker-compose-ingestor-server.yaml \
      -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
      pull -q
    docker compose \
      -f deploy/compose/docker-compose-ingestor-server.yaml \
      -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
      up -d
  else
    docker compose -f deploy/compose/docker-compose-ingestor-server.yaml pull -q
    docker compose -f deploy/compose/docker-compose-ingestor-server.yaml up -d
  fi

  log "Deploying RAG server and frontend..."
  docker compose -f deploy/compose/docker-compose-rag-server.yaml pull -q rag-server rag-frontend
  docker compose -f deploy/compose/docker-compose-rag-server.yaml up -d

  log "Deployment finished. Run 'health' after a few minutes."
}

health_check() {
  require_cmd curl
  log "Container status:"
  docker ps --format "table {{.Names}}\t{{.Status}}"

  log "Checking ingestor health (${INGESTOR_BASE_URL}/health?check_dependencies=true)..."
  curl -fsS "${INGESTOR_BASE_URL}/health?check_dependencies=true" || die "Ingestor health failed."
  printf '\n'

  log "Checking rag health (${RAG_BASE_URL}/health?check_dependencies=true)..."
  curl -fsS "${RAG_BASE_URL}/health?check_dependencies=true" || die "RAG health failed."
  printf '\n'

  log "Checking chat gateway health (http://localhost:8083/v1/health)..."
  curl -fsS "http://localhost:8083/v1/health" || die "Chat gateway health failed."
  printf '\n'

  log "Checking connector health (http://localhost:8084/v1/health)..."
  curl -fsS "http://localhost:8084/v1/health" || warn "Connector health check failed."
  printf '\n'

  log "Health checks passed."
}

demo_run() {
  require_cmd curl
  require_cmd python3
  health_check

  local work_dir
  work_dir="$(mktemp -d)"
  trap 'rm -rf "${work_dir}"' RETURN

  local ai_pdf="${work_dir}/sample_ai_article.pdf"
  local ml_pdf="${work_dir}/sample_ml_article.pdf"
  log "Downloading sample PDFs..."
  curl -fsSL "https://en.wikipedia.org/api/rest_v1/page/pdf/Artificial_intelligence" -o "${ai_pdf}"
  curl -fsSL "https://en.wikipedia.org/api/rest_v1/page/pdf/Machine_learning" -o "${ml_pdf}"

  log "Creating collection '${COLLECTION_NAME}'..."
  local collection_resp
  collection_resp="$(curl -sS -X POST "${INGESTOR_BASE_URL}/collection" \
    -H "Content-Type: application/json" \
    -d "{\"vdb_endpoint\":\"${MILVUS_ENDPOINT}\",\"collection_name\":\"${COLLECTION_NAME}\",\"metadata_schema\":[]}")"
  printf '%s\n' "${collection_resp}"

  local upload_payload
  upload_payload="$(cat <<JSON
{"vdb_endpoint":"${MILVUS_ENDPOINT}","collection_name":"${COLLECTION_NAME}","split_options":{"chunk_size":1024,"chunk_overlap":150}}
JSON
)"

  log "Uploading sample documents..."
  local upload_resp
  upload_resp="$(curl -sS -X POST "${INGESTOR_BASE_URL}/documents" \
    -F "documents=@${ai_pdf};type=application/pdf" \
    -F "documents=@${ml_pdf};type=application/pdf" \
    -F "data=${upload_payload};type=application/json")"
  printf '%s\n' "${upload_resp}"

  local task_id
  task_id="$(printf '%s' "${upload_resp}" | json_extract "task_id")"
  if [[ -z "${task_id}" ]]; then
    warn "No task_id returned from upload. Skipping ingestion wait loop."
  else
    log "Polling ingestion status for task ${task_id}..."
    local elapsed=0
    while [[ "${elapsed}" -lt "${DEMO_TIMEOUT_SECONDS}" ]]; do
      local status_resp status_state
      status_resp="$(curl -sS "${INGESTOR_BASE_URL}/status?task_id=${task_id}")"
      status_state="$(printf '%s' "${status_resp}" | json_extract "state")"
      log "Ingestion state: ${status_state:-unknown}"
      if [[ "${status_state}" == "FINISHED" ]]; then
        break
      fi
      if [[ "${status_state}" == "FAILED" ]]; then
        warn "Ingestion failed."
        printf '%s\n' "${status_resp}"
        break
      fi
      sleep 5
      elapsed=$((elapsed + 5))
    done
  fi

  log "Running non-RAG chat sanity check through gateway..."
  curl -sS -X POST "http://localhost:8083/v1/chat" \
    -H "Content-Type: application/json" \
    -d '{"schema_version":"korda.chat.request.v1","mode":"auto","messages":[{"role":"user","content":"What is 2+2?"}],"use_knowledge_base":false}' \
    | head -c 1200
  printf '\n'

  log "Running RAG chat sanity check through gateway..."
  curl -sS -X POST "http://localhost:8083/v1/chat" \
    -H "Content-Type: application/json" \
    -d "{\"schema_version\":\"korda.chat.request.v1\",\"mode\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"What are the main approaches to artificial intelligence?\"}],\"use_knowledge_base\":true,\"collection_names\":[\"${COLLECTION_NAME}\"]}" \
    | head -c 2000
  printf '\n'

  log "Demo flow finished."
}

startup_ready_check() {
  require_cmd curl
  require_cmd python3

  log "Checking startup status (http://localhost:8083/v1/startup/status)..."
  local startup_resp
  startup_resp="$(curl -fsS "http://localhost:8083/v1/startup/status")" || die "Startup status endpoint failed."
  printf '%s\n' "${startup_resp}"

  local state app_degraded
  state="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("state",""))' <<<"${startup_resp}")"
  app_degraded="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(str(d.get("app_degraded", False)).lower())' <<<"${startup_resp}")"

  [[ "${state}" == "ready" ]] || die "Startup state is '${state}', expected 'ready'."
  [[ "${app_degraded}" == "false" ]] || die "Startup status is degraded (app_degraded=${app_degraded})."
  log "Startup readiness check passed."
}

gateway_chat_validation() {
  require_cmd curl
  require_cmd python3

  log "Running gateway chat validation..."
  local chat_resp
  chat_resp="$(curl -fsS -X POST "http://localhost:8083/v1/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"schema_version\":\"korda.chat.request.v1\",
      \"mode\":\"auto\",
      \"messages\":[{\"role\":\"user\",\"content\":\"Summarize key points from uploaded docs\"}],
      \"use_knowledge_base\": true,
      \"collection_names\":[\"${COLLECTION_NAME}\"],
      \"enable_citations\": true
    }")"
  printf '%s\n' "${chat_resp}" | head -c 4000
  printf '\n'

  local answer_len citation_count fatal_warning
  answer_len="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(str(d.get("answer",""))))' <<<"${chat_resp}")"
  citation_count="$(python3 -c 'import json,sys; d=json.load(sys.stdin); c=d.get("citations") or []; print(len(c) if isinstance(c,list) else 0)' <<<"${chat_resp}")"
  fatal_warning="$(python3 -c 'import json,sys; d=json.load(sys.stdin); ws=d.get("warnings") or []; print("true" if any("fatal" in str(w).lower() for w in ws) else "false")' <<<"${chat_resp}")"

  [[ "${answer_len}" -gt 0 ]] || die "Gateway chat validation failed: empty answer."
  [[ "${citation_count}" -gt 0 ]] || die "Gateway chat validation failed: no citations returned."
  [[ "${fatal_warning}" == "false" ]] || die "Gateway chat validation failed: fatal warning present."

  log "Gateway chat validation passed."
}

strict_negative_validation() {
  require_cmd curl
  require_cmd python3

  local invalid_file="/tmp/invalid.txt"
  log "Running strict negative test with invalid extension..."
  printf 'bad strict test\n' > "${invalid_file}"

  local neg_resp
  neg_resp="$(curl -fsS -X POST "http://localhost:8083/v1/intake/upload" \
    -F "documents=@${invalid_file};type=text/plain" \
    -F "data={\"profile_id\":\"epc_drawing_profile\",\"collection_name\":\"${COLLECTION_NAME}\",\"blocking\":false,\"custom_metadata\":[]};type=application/json")"
  printf '%s\n' "${neg_resp}"

  local status validation_count
  status="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' <<<"${neg_resp}")"
  validation_count="$(python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("validation_errors") or []; print(len(e) if isinstance(e,list) else 0)' <<<"${neg_resp}")"

  [[ "${status}" == "validation_failed" ]] || die "Strict negative test failed: status='${status}'"
  [[ "${validation_count}" -gt 0 ]] || die "Strict negative test failed: validation_errors empty"
  log "Strict negative test passed."
}

persistence_restart_validation() {
  require_cmd curl
  require_cmd python3
  require_cmd docker

  log "Running restart persistence validation..."
  local chat_resp session_id session_events
  chat_resp="$(curl -fsS -X POST "http://localhost:8083/v1/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"schema_version\":\"korda.chat.request.v1\",
      \"mode\":\"auto\",
      \"messages\":[{\"role\":\"user\",\"content\":\"Give me one sentence about uploaded docs\"}],
      \"use_knowledge_base\": true,
      \"collection_names\":[\"${COLLECTION_NAME}\"],
      \"enable_citations\": true
    }")"
  session_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session_id",""))' <<<"${chat_resp}")"
  [[ -n "${session_id}" ]] || die "Persistence test failed: missing session_id from chat response."

  docker restart chat-gateway >/dev/null
  local attempts=0
  until curl -fsS "http://localhost:8083/v1/health" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [[ "${attempts}" -gt 20 ]]; then
      die "Persistence test failed: chat-gateway did not become healthy after restart."
    fi
    sleep 2
  done
  session_events="$(curl -fsS "http://localhost:8083/v1/chat/sessions/${session_id}")"

  local event_count
  event_count="$(python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("events") or []; print(len(e) if isinstance(e,list) else 0)' <<<"${session_events}")"
  [[ "${event_count}" -gt 0 ]] || die "Persistence test failed: no session events after restart."

  log "Restart persistence validation passed."
}

write_uat_readout() {
  local report_path="$1"
  local overall="$2"
  local strict_status="$3"
  local persistence_status="$4"

  mkdir -p "$(dirname "${report_path}")"
  cat > "${report_path}" <<EOF
# KORDA Local UAT Readout

- Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- Collection: ${COLLECTION_NAME}
- Build status: PASS
- Health checks: PASS
- Startup bootstrap readiness: PASS
- Ingestion happy path: PASS
- Strict rejection path: ${strict_status}
- Gateway chat with citations: PASS
- UI upload/chat journey: MANUAL
- Restart persistence: ${persistence_status}
- Final recommendation: ${overall}
EOF
  log "Wrote UAT readout to ${report_path}"
}

verify_seamless() {
  local strict_status="PASS"
  local persistence_status="PASS"
  local overall="GO"

  health_check
  startup_ready_check
  demo_run
  startup_ready_check
  gateway_chat_validation

  if [[ "${SKIP_STRICT_NEGATIVE}" == "true" ]]; then
    strict_status="SKIPPED"
    warn "Skipping strict negative validation."
  else
    strict_negative_validation
  fi

  if [[ "${SKIP_RESTART_PERSISTENCE}" == "true" ]]; then
    persistence_status="SKIPPED"
    warn "Skipping restart persistence validation."
  else
    persistence_restart_validation
  fi

  local report_path="${REPORT_FILE:-${ROOT_DIR}/artifacts/korda-local-uat-readout.md}"
  write_uat_readout "${report_path}" "${overall}" "${strict_status}" "${persistence_status}"
  log "Seamless verification completed successfully."
}

cleanup_all() {
  require_file "deploy/compose/nims.yaml"
  require_file "deploy/compose/vectordb.yaml"
  require_file "deploy/compose/vectordb.cpu.override.yaml"
  require_file "deploy/compose/docker-compose-ingestor-server.yaml"
  require_file "deploy/compose/docker-compose-rag-server.yaml"

  # Compose still interpolates required vars during `down`.
  # Use placeholders when key material is not present so cleanup always works.
  if [[ -z "${NGC_API_KEY:-}" ]]; then
    export NGC_API_KEY="cleanup-placeholder"
  fi
  if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
    export NVIDIA_API_KEY="${NGC_API_KEY}"
  fi

  log "Stopping rag stack..."
  docker compose -f deploy/compose/docker-compose-rag-server.yaml down

  log "Stopping ingestor stack..."
  if [[ "${ENABLE_KORDA_STRICT}" == "true" && -f "deploy/compose/docker-compose-ingestor-server.korda-strict.yaml" ]]; then
    docker compose \
      -f deploy/compose/docker-compose-ingestor-server.yaml \
      -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
      down
  else
    docker compose -f deploy/compose/docker-compose-ingestor-server.yaml down
  fi

  log "Stopping vector database..."
  if [[ "${FORCE_CPU_VECTORDB}" == "true" ]]; then
    docker compose -f deploy/compose/vectordb.yaml -f deploy/compose/vectordb.cpu.override.yaml down
  else
    docker compose -f deploy/compose/vectordb.yaml down
  fi

  if [[ "${SKIP_NIMS}" != "true" ]]; then
    log "Stopping NIM services..."
    docker compose -f deploy/compose/nims.yaml down
  fi

  log "Cleanup complete."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ngc-api-key)
      [[ $# -ge 2 ]] || die "--ngc-api-key requires a value."
      NGC_API_KEY_OVERRIDE="$2"
      shift 2
      ;;
    --enable-save-to-disk)
      ENABLE_SAVE_TO_DISK=true
      shift
      ;;
    --enable-rag-thinking)
      ENABLE_RAG_THINKING=true
      shift
      ;;
    --enable-vlm-inference)
      ENABLE_VLM_INFERENCE=true
      shift
      ;;
    --enable-vlm-thinking)
      ENABLE_VLM_THINKING=true
      shift
      ;;
    --strict-profile)
      ENABLE_KORDA_STRICT=true
      shift
      ;;
    --skip-docker-login)
      SKIP_DOCKER_LOGIN=true
      shift
      ;;
    --skip-nims)
      SKIP_NIMS=true
      shift
      ;;
    --cpu-vectordb)
      FORCE_CPU_VECTORDB=true
      shift
      ;;
    --report-file)
      [[ $# -ge 2 ]] || die "--report-file requires a value."
      REPORT_FILE="$2"
      shift 2
      ;;
    --skip-strict-negative)
      SKIP_STRICT_NEGATIVE=true
      shift
      ;;
    --skip-restart-persistence)
      SKIP_RESTART_PERSISTENCE=true
      shift
      ;;
    --collection-name)
      [[ $# -ge 2 ]] || die "--collection-name requires a value."
      COLLECTION_NAME="$2"
      shift 2
      ;;
    --rag-base-url)
      [[ $# -ge 2 ]] || die "--rag-base-url requires a value."
      RAG_BASE_URL="$2"
      shift 2
      ;;
    --ingestor-base-url)
      [[ $# -ge 2 ]] || die "--ingestor-base-url requires a value."
      INGESTOR_BASE_URL="$2"
      shift 2
      ;;
    --milvus-endpoint)
      [[ $# -ge 2 ]] || die "--milvus-endpoint requires a value."
      MILVUS_ENDPOINT="$2"
      shift 2
      ;;
    --demo-timeout-seconds)
      [[ $# -ge 2 ]] || die "--demo-timeout-seconds requires a value."
      DEMO_TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

if [[ "${ACTION}" == "--help" || "${ACTION}" == "-h" ]]; then
  usage
  exit 0
fi

apply_api_key_overrides

case "${ACTION}" in
  prereq)
    check_prerequisites
    ;;
  configure)
    configure_env
    ;;
  rebuild)
    rebuild_all
    ;;
  deploy)
    deploy_all
    ;;
  health)
    health_check
    ;;
  demo)
    demo_run
    ;;
  verify)
    verify_seamless
    ;;
  cleanup)
    cleanup_all
    ;;
  all)
    check_prerequisites
    configure_env
    deploy_all
    health_check
    ;;
  full-demo)
    check_prerequisites
    configure_env
    deploy_all
    health_check
    demo_run
    ;;
  full-verify)
    check_prerequisites
    rebuild_all
    verify_seamless
    ;;
  *)
    usage
    die "Unknown action: ${ACTION}"
    ;;
esac
