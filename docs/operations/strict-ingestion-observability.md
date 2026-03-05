# Strict Ingestion Observability (Stage/Prod)

This runbook defines KPIs and alerts for strict ingestion validation.

## Metrics emitted by ingestor

- `strict_validation_records_total{phase,outcome,error_code,document_class}`
- `metadata_enrichment_jobs_total{status,document_class}`
- `metadata_enrichment_duration_ms`

`phase` values:
- `caption`
- `summary`
- `metadata`

## Dashboard

Helm-managed dashboard ConfigMap is enabled via overlay toggle:
- `strictObservability.enabled: true` (stage/prod)

Raw dashboard artifact:
- `deploy/config/korda-strict-ingestion-dashboard.json`

Dashboard includes:
- strict validation failure rate
- failure rate by `error_code`
- failure rate by `document_class`
- metadata enrichment success rate
- metadata enrichment duration trend

## Alert rules

Helm-managed PrometheusRule is enabled via overlay toggle:
- `strictObservability.enabled: true` (stage/prod)

Optional direct apply:

```bash
kubectl apply -f deploy/config/korda-strict-validation-alerts.yaml
```

Rules include:
- `KordaStrictValidationFailureRateHigh`
- `KordaStrictValidationErrorCodeSpike`
- `KordaMetadataEnrichmentFailureRateHigh`
- `KordaMetadataEnrichmentLatencyHigh`

## Stage/Prod checklist

1. Ensure ingestor `/metrics` is scraped by Prometheus.
2. Import the strict ingestion dashboard JSON.
3. Apply alert rules and route to on-call.
4. Validate alerts in stage before prod enablement.
5. Keep strict-ingestion CI green (`.github/workflows/strict-ingestion-ci.yml`) before promotion.
