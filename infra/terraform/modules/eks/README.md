# Module: eks

Creates a private-endpoint EKS cluster for KORDA RAG:

- Control plane logs enabled
- Encryption for Kubernetes secrets via KMS
- IRSA enabled
- CPU node group for app/control workloads
- GPU node group for Milvus and GPU-bound workloads

Public API endpoint access is disabled by default.
