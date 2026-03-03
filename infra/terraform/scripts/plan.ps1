param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("dev", "stage", "prod")]
  [string]$Environment,

  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$envDir = Join-Path $PSScriptRoot "..\envs\$Environment"
$envDir = Resolve-Path $envDir

Push-Location $envDir
try {
  if (-not (Test-Path ".\backend.hcl")) {
    Write-Host "Missing backend.hcl in $envDir. Copy backend.hcl.example to backend.hcl and set state backend values."
    exit 1
  }

  terraform init -backend-config=backend.hcl
  terraform validate
  terraform plan -out=tfplan

  if ($Apply) {
    terraform apply tfplan
  }
}
finally {
  Pop-Location
}
