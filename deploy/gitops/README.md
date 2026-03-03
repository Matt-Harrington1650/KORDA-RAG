# GitOps Layout (Argo CD)

This directory defines GitOps deployment for `dev`, `stage`, and `prod`.

## Structure

- `argocd/projects`: Argo CD project definitions.
- `argocd/apps/root-*.yaml`: Root app-of-apps per environment.
- `argocd/apps/<env>`: Environment-specific Application objects.
- `bootstrap/*`: Namespaces and ExternalSecret resources.

## Bootstrap order

1. Apply AppProject.
2. Apply `root-dev.yaml`, `root-stage.yaml`, or `root-prod.yaml`.
3. Argo CD sync wave ordering handles platform -> policies -> app.
