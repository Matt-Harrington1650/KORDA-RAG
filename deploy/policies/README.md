# Policy Bundles

- `kyverno/`: admission and compliance policies.
- `network/dev|stage|prod/`: namespace-scoped default deny and allowlist egress policies.

These manifests are consumed by Argo CD applications under `deploy/gitops/argocd/apps/<env>`.
