#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "Stopping RAG server and frontend..."
docker compose -f deploy/compose/docker-compose-rag-server.yaml down

echo "Stopping ingestor stack..."
docker compose \
  -f deploy/compose/docker-compose-ingestor-server.yaml \
  -f deploy/compose/docker-compose-ingestor-server.korda-strict.yaml \
  down

echo "Stopping vector database dependencies..."
docker compose -f deploy/compose/vectordb.yaml down

echo "Shutdown complete."
