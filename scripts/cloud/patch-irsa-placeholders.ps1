param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("dev", "stage", "prod")]
  [string]$Environment,

  [Parameter(Mandatory = $true)]
  [string]$RagServerRoleArn,

  [Parameter(Mandatory = $true)]
  [string]$IngestorServerRoleArn,

  [Parameter(Mandatory = $true)]
  [string]$ExternalSecretsRoleArn
)

$ErrorActionPreference = "Stop"

$overlayFile = "deploy/helm/overlays/$Environment.yaml"
$externalSecretsAppFile = "deploy/gitops/argocd/apps/$Environment/01-external-secrets.yaml"

if (-not (Test-Path $overlayFile)) {
  throw "Overlay not found: $overlayFile"
}

if (-not (Test-Path $externalSecretsAppFile)) {
  throw "Argo app file not found: $externalSecretsAppFile"
}

$overlay = Get-Content $overlayFile -Raw
$overlay = $overlay.Replace("<RAG_SERVER_IRSA_ROLE_ARN>", $RagServerRoleArn)
$overlay = $overlay.Replace("<INGESTOR_SERVER_IRSA_ROLE_ARN>", $IngestorServerRoleArn)
Set-Content -Path $overlayFile -Value $overlay -NoNewline

$externalSecretsApp = Get-Content $externalSecretsAppFile -Raw
$externalSecretsApp = $externalSecretsApp.Replace("<EXTERNAL_SECRETS_ROLE_ARN>", $ExternalSecretsRoleArn)
Set-Content -Path $externalSecretsAppFile -Value $externalSecretsApp -NoNewline

Write-Host "Patched IRSA placeholders for environment: $Environment"
