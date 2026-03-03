# Module: secrets

Creates Secrets Manager secret *containers* only (no values):

- NGC API key for image pulls and NVIDIA-hosted APIs
- Service-specific model API keys (LLM, embeddings, reranker, VLM, etc.)

Populate secret values using a secure out-of-band process after `terraform apply`.
