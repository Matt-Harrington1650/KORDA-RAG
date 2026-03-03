# Incident Runbooks

## 1. API Outage (`rag-server` or `ingestor-server`)

1. Confirm pod and deployment status:
   - `kubectl get pods -n <ns>`
   - `kubectl describe pod <pod> -n <ns>`
2. Validate dependency health:
   - Milvus, Redis, external endpoints
3. Check recent rollout in Argo CD.
4. Roll back to last known good revision if needed.
5. Capture timeline, root cause, and mitigation.

## 2. NVIDIA API Rate Limiting / Upstream Failure

1. Identify endpoint failures from logs and metrics.
2. Reduce parallel ingestion (`NV_INGEST_CONCURRENT_BATCHES`, `NV_INGEST_FILES_PER_BATCH`).
3. Temporarily disable high-cost features (reflection/decomposition/VLM) by env override.
4. If persistent, switch to retrieval-only mode for continuity.

## 3. Milvus Degradation

1. Check Milvus pod health and GPU availability.
2. Verify persistence volumes and disk pressure.
3. Run retrieval smoke query on known collection.
4. Scale read workload down and re-index if corruption is suspected.

## 4. Ingestion Backlog

1. Inspect queue depth and worker utilization.
2. Increase batch workers within memory limits.
3. Throttle ingestion clients if queue growth exceeds threshold.
4. Track completion SLA impact and communicate ETA.
