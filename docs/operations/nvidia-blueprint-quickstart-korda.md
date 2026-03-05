# Click-by-Click Functional Test Runbook (Windows + WSL + Docker Desktop)

## Summary
Use this flow to run your existing local KORDA tools app (`C:\code\KORDA-RAG`) with NVIDIA-hosted endpoints and CPU-safe local vector DB:

1. `configure`
2. `rebuild`
3. `verify`
4. manual UI UAT
5. `cleanup`

The local app now includes:
1. `chat-gateway` auto startup bootstrap (`/v1/startup/status`).
2. `intake-connector` warm-run + poll worker.
3. Frontend gateway-first routing for `/api/chat` and `/api/intake/*`.
4. Automated seamless verification action with UAT readout output.

This runbook fixes common failures seen in practice:

1. Running PowerShell commands from WSL bash.
2. Docker Desktop service check false-blocking wrapper runs.
3. `--skip-nims` with local endpoint defaults.
4. Credential-helper pull errors for `rag-server` / `rag-frontend`.

## Choose One Shell Mode
Do not mix command syntaxes.

1. If your prompt looks like `mharrington@...$`, use **WSL bash** commands only.
2. If your prompt looks like `PS C:\...>`, use **PowerShell** commands only.

## Track A (Recommended): WSL Bash End-to-End

### 1. Start Docker Desktop
1. Click **Start**.
2. Open **Docker Desktop**.
3. Wait for engine running.
4. Open **Settings -> Resources -> WSL Integration**.
5. Enable your distro (`Ubuntu`).
6. Click **Apply & Restart**.

### 2. Open WSL and move to repo
1. Click **Start**.
2. Open **Ubuntu**.
3. Run:

```bash
cd /mnt/c/code/KORDA-RAG
```

### 3. Set key and verify NVCR login
1. Run:

```bash
export NGC_API_KEY="nvapi-REPLACE_ME"
printf '%s' "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
```

2. Pass criteria:
1. Output includes `Login Succeeded`.

### 4. Configure hosted profile
1. Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh configure --ngc-api-key "$NGC_API_KEY"
```

2. What this sets:
1. Hosted LLM/summary/embedding/reranker URLs.
2. Hosted OCR/page/table/graphic extraction endpoints.
3. Strict ingestion + metadata enrichment defaults (`INGESTION_JSON_STRICT_MODE=True`, `ENABLE_METADATA_ENRICHMENT=True`).
4. Full multimodal extraction defaults (`APP_NVINGEST_EXTRACTIMAGES=True`).
5. Retrieval/quality defaults (`ENABLE_QUERYREWRITER=True`, `CONVERSATION_HISTORY=4`, `ENABLE_REFLECTION=True`, `ENABLE_QUERY_DECOMPOSITION=True`).
6. KORDA quickstart env block in `deploy/compose/.env`.

### 5. Pre-pull RAG images (avoids intermittent credential-helper pull errors)
Run:

```bash
docker pull nvcr.io/nvidia/blueprint/rag-server:2.4.0
docker pull nvcr.io/nvidia/blueprint/rag-frontend:2.4.0
```

### 6. Deploy services
Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh deploy --ngc-api-key "$NGC_API_KEY" --skip-nims --cpu-vectordb
```

Notes:
1. `--skip-nims` skips local embedding/ranking/OCR/page-elements containers.
2. `--cpu-vectordb` forces CPU-safe Milvus in WSL/non-GPU setups.

### 6b. Deterministic rebuild (recommended)
Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh rebuild --ngc-api-key "$NGC_API_KEY" --skip-nims --cpu-vectordb
```

What it does:
1. `cleanup`
2. `configure`
3. local image build (`rag-frontend`, `chat-gateway`, `intake-connector`)
4. `deploy`

### 7. Wait and check health
Run:

```bash
sleep 45
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh health --ngc-api-key "$NGC_API_KEY"
```

If you see `connection reset by peer`, wait 30-60s and run health again.

### 8. Run demo
Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh demo --collection-name multimodal_data --ngc-api-key "$NGC_API_KEY"
```

Pass criteria:
1. Collection create succeeds.
2. Upload returns `task_id`.
3. Status reaches `FINISHED`.
4. Non-RAG and RAG chat calls return responses.
5. Demo uses `POST /v1/collection` (non-deprecated bootstrap path).

### 8b. Run seamless verification (automated)
Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh verify --collection-name multimodal_data --report-file artifacts/korda-local-uat-readout.md
```

This includes:
1. Health checks for `8081/8082/8083/8084`.
2. Startup readiness gate (`state=ready`, `app_degraded=false`).
3. Demo ingestion and gateway chat checks.
4. Strict negative test (`/v1/intake/upload` with invalid extension).
5. Restart persistence test (`docker restart chat-gateway` + session replay).
6. UAT readout output at `artifacts/korda-local-uat-readout.md`.
7. Template available at `docs/operations/korda-local-uat-readout-template.md`.

Optional flags:
1. `--skip-strict-negative`
2. `--skip-restart-persistence`

### 9. Manual smoke checks
Run:

```bash
curl "http://localhost:8082/v1/health?check_dependencies=true"
curl "http://localhost:8081/v1/health?check_dependencies=true"
curl "http://localhost:8083/v1/health"
curl "http://localhost:8083/v1/startup/status"
curl "http://localhost:8084/v1/health"
```

Open UI:
1. Open browser.
2. Go to `http://localhost:8090`.
3. Upload one file.
4. Ask one query.

### 10. Cleanup
Run:

```bash
bash scripts/cloud/nvidia-rag-blueprint-quickstart.sh cleanup --skip-nims --cpu-vectordb
```

## Manual UI UAT (Click-by-Click)
1. Open browser and go to `http://localhost:8090`.
2. Confirm page loads and no blocking errors.
3. Use existing collection (`multimodal_data`) or create one.
4. Upload 1-2 files using Add Sources/upload flow.
5. Open notifications/tasks and wait for `FINISHED`.
6. Ask: `Summarize the uploaded document and cite sources`.
7. Confirm response appears and citations are shown.
8. Ask a second follow-up question.
9. Confirm response continuity.
10. Mark UI journey as pass/fail in readout.

## Track B: Windows PowerShell Wrapper
Use this only from `PS C:\...>` prompt.

1. Open **Windows PowerShell**.
2. Run:

```powershell
cd C:\code\KORDA-RAG
$env:NGC_API_KEY="nvapi-REPLACE_ME"
```

3. Configure:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud\nvidia-rag-blueprint-quickstart.ps1 -Action configure -NgcApiKey $env:NGC_API_KEY -SkipDockerDesktopCheck
```

4. Deploy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud\nvidia-rag-blueprint-quickstart.ps1 -Action deploy -NgcApiKey $env:NGC_API_KEY -SkipDockerDesktopCheck -SkipNims -CpuVectordb
```

5. Health + Demo + Verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud\nvidia-rag-blueprint-quickstart.ps1 -Action health -NgcApiKey $env:NGC_API_KEY -SkipDockerDesktopCheck
powershell -ExecutionPolicy Bypass -File .\scripts\cloud\nvidia-rag-blueprint-quickstart.ps1 -Action demo -CollectionName multimodal_data -NgcApiKey $env:NGC_API_KEY -SkipDockerDesktopCheck
powershell -ExecutionPolicy Bypass -File .\scripts\cloud\nvidia-rag-blueprint-quickstart.ps1 -Action verify -CollectionName multimodal_data -ReportFile "C:\code\KORDA-RAG\artifacts\korda-local-uat-readout.md" -NgcApiKey $env:NGC_API_KEY -SkipDockerDesktopCheck
```

## Troubleshooting

### `Command 'powershell' not found`
You are in WSL bash. Use Track A commands.

### `Docker Desktop service (com.docker.service) is not running`
Use `-SkipDockerDesktopCheck` in `.ps1` wrapper or use Track A.

### `error getting credentials - err: exit status 1`
Run:

```bash
docker logout nvcr.io
printf '%s' "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
docker pull nvcr.io/nvidia/blueprint/rag-server:2.4.0
docker pull nvcr.io/nvidia/blueprint/rag-frontend:2.4.0
```

Then rerun deploy.

### `curl: (56) Recv failure: Connection reset by peer`
Ingestor is still starting. Wait 30-60 seconds and rerun health.

### Ingestor health shows unresolved local NIM hosts
Rerun `configure` to re-stamp hosted endpoint block into `deploy/compose/.env`, then redeploy.

## Security Note
If any `nvapi-...` key was pasted into terminal logs/chat/tickets, rotate it immediately in NGC and use a new key.
