param(
  [Parameter(Mandatory = $true)]
  [string]$Namespace,

  [string]$RagBaseUrl = "http://localhost:8081/v1",
  [string]$IngestorBaseUrl = "http://localhost:8082/v1"
)

$ErrorActionPreference = "Stop"
$failedChecks = @()

function Test-HttpHealth {
  param(
    [string]$Name,
    [string]$Url
  )

  try {
    $resp = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 30
    if (-not $resp.message) {
      $failedChecks += "$Name health response missing message"
      return
    }
    Write-Host "[PASS] $Name health: $($resp.message)"
  }
  catch {
    $failedChecks += "$Name health check failed: $($_.Exception.Message)"
  }
}

Write-Host "Checking Kubernetes pods in namespace $Namespace..."
$pods = kubectl get pods -n $Namespace --no-headers 2>$null
if (-not $pods) {
  $failedChecks += "No pods found in namespace $Namespace or kubectl access failed."
}
else {
  $notRunning = @($pods | Where-Object { $_ -notmatch "\sRunning\s" -and $_ -notmatch "\sCompleted\s" })
  if ($notRunning.Count -gt 0) {
    $failedChecks += "Non-running pods detected: $($notRunning -join '; ')"
  }
  else {
    Write-Host "[PASS] All pods are Running/Completed in $Namespace"
  }
}

Write-Host "Checking required secrets..."
$requiredSecrets = @("ngc-api", "ngc-secret", "rag-api-keys")
foreach ($secret in $requiredSecrets) {
  $exists = kubectl get secret $secret -n $Namespace --ignore-not-found -o name 2>$null
  if (-not $exists) {
    $failedChecks += "Missing secret: $secret in namespace $Namespace"
  }
  else {
    Write-Host "[PASS] Secret exists: $secret"
  }
}

Test-HttpHealth -Name "RAG" -Url "$RagBaseUrl/health?check_dependencies=true"
Test-HttpHealth -Name "Ingestor" -Url "$IngestorBaseUrl/health?check_dependencies=true"

if ($failedChecks.Count -gt 0) {
  Write-Host ""
  Write-Host "Promotion gate checks failed:" -ForegroundColor Red
  $failedChecks | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
  exit 1
}

Write-Host ""
Write-Host "All promotion gate checks passed." -ForegroundColor Green
