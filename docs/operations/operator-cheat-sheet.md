# Operator Cheat Sheet: UI Toggles -> Backend Env Vars

This page maps user-facing controls in the current RAG UI to backend request fields, environment variables, and recommended values for `dev`, `stage`, and `prod`.

## Scope

- UI controls from `Settings` and `Collection Configuration`.
- Request payload mappings from `frontend/src/hooks/useMessageSubmit.ts` and upload hooks.
- Backend defaults from `src/nvidia_rag/utils/configuration.py`.
- Current deployment pins from:
  - `deploy/helm/nvidia-blueprint-rag/values.yaml`
  - `deploy/helm/overlays/dev.yaml`
  - `deploy/helm/overlays/stage.yaml`
  - `deploy/helm/overlays/prod.yaml`

## Important Behavior

- The frontend omits undefined/empty values from requests.
- Boolean feature toggles are always sent when present, including explicit `false`.
- If an env var is not pinned in an overlay, the chart default is used.

## 1) User Toggle Matrix

| UI Toggle | Frontend State Key | Request Field | Backend Env Var(s) | Current Base/Overlay State | Recommended Dev | Recommended Stage | Recommended Prod | Operational Impact |
|---|---|---|---|---|---|---|---|---|
| Enable Reranker | `enableReranker` | `enable_reranker` | `ENABLE_RERANKER` | Chart default `True`; not explicitly pinned per env | `true` | `true` | `true` | Improves relevance, adds latency/cost. Keep on for regulated-answer quality. |
| Include Citations | `includeCitations` | `enable_citations` | `ENABLE_CITATIONS` | Chart default `True`; not explicitly pinned per env | `true` | `true` | `true` | Required for traceability/auditability of responses. |
| Use Guardrails | `useGuardrails` | `enable_guardrails` | `ENABLE_GUARDRAILS` | Chart default `False`; not explicitly pinned per env | `false` | `true` | `true` | Safety/compliance filtering. Can block unsafe output; tune prompts/policies in stage first. |
| Query Rewriting | `enableQueryRewriting` | `enable_query_rewriting` | `ENABLE_QUERYREWRITER`, `APP_QUERYREWRITER_MODELNAME`, `APP_QUERYREWRITER_SERVERURL` | Chart default `False`; overlays do not pin toggle | `false` | `true` | `true` | Better recall for ambiguous queries, but adds one extra LLM call and latency. |
| VLM Inference | `enableVlmInference` | `enable_vlm_inference` | `ENABLE_VLM_INFERENCE`, `VLM_TO_LLM_FALLBACK`, `APP_VLM_MODELNAME`, `APP_VLM_SERVERURL` | Pinned: dev `false`, stage `true`, prod `true`; fallback pinned `true` in stage/prod | `false` | `true` | `true` | Required for image-aware queries. Higher token/image cost when enabled. |
| Filter Generator | `enableFilterGenerator` | `enable_filter_generator` | `ENABLE_FILTER_GENERATOR`, `APP_FILTEREXPRESSIONGENERATOR_MODELNAME`, `APP_FILTEREXPRESSIONGENERATOR_SERVERURL` | Chart default `False`; overlays do not pin toggle | `false` | `true` | `true` | Converts NL query intent into metadata filters. Can over-filter if metadata quality is weak. |
| Document Summarization (per collection) | `generateSummary` | `generate_summary` (ingestion metadata) | Behavior/tuning via `SUMMARY_LLM*`, `SUMMARY_MAX_PARALLELIZATION` | UI default for new collections is `true`; overlays keep summarizer endpoint as hosted (`SUMMARY_LLM_SERVERURL: ""`) | `false` | `true` | `true` | Adds ingestion time and inference cost; improves browseability and downstream retrieval context. |
| Use Local Storage | `useLocalStorage` | N/A | N/A | UI-only persistence control | `true` | `false` | `false` | No backend effect. In shared environments this can retain sensitive prompts/settings locally. |
| Theme | `theme` | N/A | N/A | UI-only | Any | Any | Any | No backend effect. |

## 2) Agentic Pipeline Toggles (Operator-Level)

These are not currently exposed as primary user toggles in Settings, but they are core RAG agent controls for KORDA operations.

| Capability | Env Var(s) | Current Overlay Pins | Recommended Dev | Recommended Stage | Recommended Prod | Operational Impact |
|---|---|---|---|---|---|---|
| Query Decomposition | `ENABLE_QUERY_DECOMPOSITION`, `MAX_RECURSION_DEPTH` | dev `false`; stage `true` depth `2`; prod `true` depth `3` | `false`, depth `3` | `true`, depth `2` | `true`, depth `3` | Improves multi-hop QA accuracy; increases retrieval calls and latency. |
| Self-Reflection | `ENABLE_REFLECTION`, `MAX_REFLECTION_LOOP`, `REFLECTION_LLM`, `REFLECTION_LLM_SERVERURL` | dev `false`; stage `true` loop `2`; prod `true` loop `3` | `false`, loop `3` | `true`, loop `2` | `true`, loop `3` | Improves groundedness and relevance; each loop adds generation latency/cost. |
| VLM Text Fallback | `VLM_TO_LLM_FALLBACK` | stage/prod pinned `true` | `true` | `true` | `true` | Keeps text-only prompts on standard LLM path when VLM is enabled. |
| Post-Ingest Metadata Enrichment | `ENABLE_METADATA_ENRICHMENT`, `METADATA_EXTRACTION_LLM`, `METADATA_EXTRACTION_LLM_SERVERURL`, `METADATA_EXTRACTION_MIN_SOURCE_QUALITY` | dev `false`; stage/prod `true` | `false`, quality `0.75` | `true`, quality `0.78` | `true`, quality `0.80` | Adds document-level structured metadata extraction and strict validation/error visibility. |

## 3) Non-Toggle User Controls -> Env Mapping

### Retrieval and generation sliders/inputs

| UI Control | Frontend Key | Request Field | Backend Env Var | Current Pins | Recommended Dev | Recommended Stage | Recommended Prod |
|---|---|---|---|---|---|---|---|
| Temperature | `temperature` | `temperature` | `LLM_TEMPERATURE` | Chart `0`; not overlay-pinned | `0.0` | `0.0` | `0.0` |
| Top P | `topP` | `top_p` | `LLM_TOP_P` | Chart `1.0`; not overlay-pinned | `1.0` | `1.0` | `1.0` |
| Max Tokens | `maxTokens` | `max_tokens` | `LLM_MAX_TOKENS` | Chart `32768`; not overlay-pinned | `32768` | `32768` | `32768` |
| Vector DB Top K | `vdbTopK` | `vdb_top_k` | `VECTOR_DB_TOPK` | dev/stage inherit `100`; prod pinned `120` | `100` | `100` | `120` |
| Reranker Top K | `rerankerTopK` | `reranker_top_k` | `APP_RETRIEVER_TOPK` | dev/stage inherit `10`; prod pinned `12` | `10` | `10` | `12` |
| Confidence Score Threshold | `confidenceScoreThreshold` | `confidence_threshold` | `RERANKER_CONFIDENCE_THRESHOLD` | dev/stage inherit `0.0`; prod pinned `0.2` | `0.0` | `0.1` | `0.2` |

### Model selectors

| UI Control | Frontend Key | Request Field | Backend Env Var | Current Default |
|---|---|---|---|---|
| LLM Model | `model` | `model` | `APP_LLM_MODELNAME` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` |
| Embedding Model | `embeddingModel` | `embedding_model` | `APP_EMBEDDINGS_MODELNAME` | `nvidia/llama-3.2-nv-embedqa-1b-v2` |
| Reranker Model | `rerankerModel` | `reranker_model` | `APP_RANKING_MODELNAME` | `nvidia/llama-3.2-nv-rerankqa-1b-v2` |
| VLM Model | `vlmModel` | `vlm_model` | `APP_VLM_MODELNAME` | `nvidia/nemotron-nano-12b-v2-vl` |

### Endpoint inputs

| UI Control | Frontend Key | Request Field | Backend Env Var | Recommended Cloud Pattern |
|---|---|---|---|---|
| LLM Endpoint | `llmEndpoint` | `llm_endpoint` | `APP_LLM_SERVERURL` | `""` for NVIDIA-hosted endpoint routing |
| Embedding Endpoint | `embeddingEndpoint` | `embedding_endpoint` | `APP_EMBEDDINGS_SERVERURL` | `https://integrate.api.nvidia.com/v1` |
| Reranker Endpoint | `rerankerEndpoint` | `reranker_endpoint` | `APP_RANKING_SERVERURL` | `""` for NVIDIA-hosted endpoint routing |
| VLM Endpoint | `vlmEndpoint` | `vlm_endpoint` | `APP_VLM_SERVERURL` | `""` for NVIDIA-hosted endpoint routing |
| Vector DB Endpoint | `vdbEndpoint` | `vdb_endpoint` | `APP_VECTORSTORE_URL` | Internal Milvus service URL only (private networking) |

### Advanced settings

| UI Control | Frontend Key | Request Field | Backend Env Var | Notes |
|---|---|---|---|---|
| Stop Tokens | `stopTokens` | `stop` | N/A (request-time only) | Use for per-request generation termination behavior. |

## 4) Recommended Overlay Pinning

To reduce drift between envs, pin all critical toggles explicitly in each overlay (do not rely on chart defaults for regulated workloads), especially:

- `ENABLE_GUARDRAILS`
- `ENABLE_QUERYREWRITER`
- `ENABLE_FILTER_GENERATOR`
- `ENABLE_RERANKER`
- `ENABLE_CITATIONS`
- `ENABLE_VLM_INFERENCE`
- `ENABLE_QUERY_DECOMPOSITION`
- `ENABLE_REFLECTION`
- `ENABLE_METADATA_ENRICHMENT`
- `METADATA_EXTRACTION_MIN_SOURCE_QUALITY`

Also keep retrieval thresholds explicitly pinned:

- `APP_RETRIEVER_TOPK`
- `VECTOR_DB_TOPK`
- `RERANKER_CONFIDENCE_THRESHOLD`
