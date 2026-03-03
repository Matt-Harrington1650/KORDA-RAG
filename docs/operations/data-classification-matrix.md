# Data Classification Matrix (KORDA RAG)

| Class | Description | Example | Allowed Storage | Retention | Deletion SLA |
|---|---|---|---|---|---|
| `PUBLIC` | Non-sensitive published content | Public docs, manuals | S3/MinIO, Milvus, logs | 365 days | 30 days |
| `INTERNAL` | Business-internal content | Internal SOPs | S3/MinIO, Milvus, logs | 180 days | 14 days |
| `CONFIDENTIAL` | Restricted business content | Contract PDFs | Encrypted S3/MinIO, Milvus | 90 days | 7 days |
| `REGULATED` | Controlled sensitive content | Legal/regulatory records | Encrypted storage only, limited logs | Policy-bound | 72 hours |

## Legal Hold

- Legal hold overrides scheduled deletion.
- Hold tags must be tracked in collection metadata.

## Metadata Requirements

Required metadata fields during ingestion:

- `classification`
- `owner`
- `retention_days`
- `legal_hold` (`true|false`)
