# Disaster Recovery Playbook

## Targets

- RTO: 4 hours (stage target), 2 hours (prod target)
- RPO: 1 hour

## Covered Components

- Milvus persistent data
- Object storage artifacts (MinIO/S3-compatible)
- Kubernetes manifests and configuration from Git

## Backup Requirements

- Daily backup for vector/object data.
- Hourly metadata snapshots for active collections.
- Immutable retention on backup bucket.

## Restore Procedure (Non-Prod Drill)

1. Provision clean namespace or clean cluster env.
2. Restore object and vector data from latest valid backup.
3. Reconcile manifests via Argo CD.
4. Run smoke tests:
   - health endpoints
   - known retrieval query
   - known generation query with citation
5. Record restore duration and data freshness.

## Evidence

- Backup job logs
- Restore execution logs
- Smoke test results
- Sign-off artifact attached to release record
