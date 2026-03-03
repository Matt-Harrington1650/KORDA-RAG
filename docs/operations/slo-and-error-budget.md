# SLO and Error Budget Baseline

## SLOs

### API Availability

- SLO: 99.5% monthly availability for `rag-server` and `ingestor-server`.
- Measure: successful responses / total requests from service metrics.

### Query Latency

- SLO: p95 latency
  - `/v1/search` <= 2.5s
  - `/v1/generate` <= 8.0s

### Ingestion Completion

- SLO: 95% of files < 50MB complete ingestion in <= 10 minutes.

## Error Budget Policy

- Monthly error budget for 99.5% availability: ~3h 39m.
- Burn threshold:
  - 50% consumed in 7 days -> freeze feature releases in that env.
  - 75% consumed in 14 days -> incident review and rollback plan.

## Ownership

- Primary: Platform Engineering
- Secondary: Applied AI / RAG Application Team
- Escalation: Security + SRE for regulated incidents
