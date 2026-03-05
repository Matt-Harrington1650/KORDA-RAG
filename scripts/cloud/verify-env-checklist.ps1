param(
  [ValidateSet("dev", "stage", "prod", "all")]
  [string]$Environment = "all",

  [string]$RagBaseUrl = "http://localhost:8081/v1",
  [string]$IngestorBaseUrl = "http://localhost:8082/v1",
  [string]$CollectionName = "multimodal_data",

  [string]$DevNamespace = "rag-dev",
  [string]$StageNamespace = "rag-stage",
  [string]$ProdNamespace = "rag-prod",

  [switch]$SkipStrictFixtureTests
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")

$envMatrix = @{
  dev = @{
    Namespace = $DevNamespace
    Overlay = Join-Path $repoRoot "deploy\helm\overlays\dev.yaml"
    PromotionGate = "Dev -> Stage"
  }
  stage = @{
    Namespace = $StageNamespace
    Overlay = Join-Path $repoRoot "deploy\helm\overlays\stage.yaml"
    PromotionGate = "Stage -> Prod"
  }
  prod = @{
    Namespace = $ProdNamespace
    Overlay = Join-Path $repoRoot "deploy\helm\overlays\prod.yaml"
    PromotionGate = "Production runtime"
  }
}

function Assert-OverlayControl {
  param(
    [string]$OverlayPath,
    [string]$EnvironmentName
  )

  if (-not (Test-Path $OverlayPath)) {
    throw "Overlay file not found for ${EnvironmentName}: $OverlayPath"
  }

  $content = Get-Content -Path $OverlayPath -Raw
  $requiredPatterns = @(
    "PROMPT_CONFIG_FILE:\s*""/prompt-korda-epc.yaml""",
    "INGESTION_JSON_STRICT_MODE:\s*""True""",
    "INGESTION_CAPTION_MIN_CONFIDENCE:\s*""0.80""",
    "INGESTION_SUMMARY_MIN_CONFIDENCE:\s*""0.85""",
    "INGESTION_CAPTION_MIN_CONFIDENCE_BY_ARTIFACT:\s*[""'].*[""']",
    "INGESTION_SUMMARY_MIN_CONFIDENCE_BY_DOCUMENT_TYPE:\s*[""'].*[""']",
    "INGESTION_FAIL_ON_MISSING_CRITICAL:\s*""True""",
    "ENABLE_METADATA_ENRICHMENT:\s*""(True|False)""",
    "METADATA_EXTRACTION_MIN_SOURCE_QUALITY:\s*""0\.[0-9]+"""
  )

  foreach ($pattern in $requiredPatterns) {
    if ($content -notmatch $pattern) {
      throw "Overlay $EnvironmentName missing required control: $pattern"
    }
  }

  if ($content -notmatch "(?ms)strictObservability:\s*\r?\n\s*enabled:\s*(true|false)") {
    throw "Overlay $EnvironmentName missing strictObservability.enabled toggle."
  }

  if ($EnvironmentName -in @("stage", "prod")) {
    if ($content -notmatch "(?ms)strictObservability:\s*\r?\n\s*enabled:\s*true") {
      throw "Overlay $EnvironmentName must enable strictObservability."
    }
    if ($content -notmatch "ENABLE_METADATA_ENRICHMENT:\s*""True""") {
      throw "Overlay $EnvironmentName must enable metadata enrichment."
    }
    if ($content -match "INGESTION_CAPTION_MIN_CONFIDENCE_BY_ARTIFACT:\s*[""']\{\}[""']") {
      throw "Overlay $EnvironmentName must define non-empty caption per-artifact thresholds."
    }
    if ($content -match "INGESTION_SUMMARY_MIN_CONFIDENCE_BY_DOCUMENT_TYPE:\s*[""']\{\}[""']") {
      throw "Overlay $EnvironmentName must define non-empty summary per-document thresholds."
    }
  }

  Write-Host "[PASS] Overlay controls verified for $EnvironmentName -> $OverlayPath"
}

function Invoke-StrictFixtureSmokeTests {
  param(
    [string]$RepoRoot
  )

  if ($SkipStrictFixtureTests) {
    Write-Host "[SKIP] Strict fixture smoke tests disabled."
    return
  }

  Write-Host "Running strict fixture smoke tests..."
  try {
    & python -c "import pytest, fastapi" | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Missing Python test dependencies."
    }
  }
  catch {
    throw "Strict fixture smoke tests require pytest and fastapi in the active Python environment. Install test dependencies or rerun with -SkipStrictFixtureTests."
  }

  Push-Location $RepoRoot
  try {
    & python -m pytest `
      tests/unit/test_ingestor_server/test_strict_ingestion_api_smoke.py `
      tests/unit/test_utils/test_ingestion_validation.py `
      tests/unit/test_utils/test_metadata_enrichment.py `
      --maxfail=1 -q
    if ($LASTEXITCODE -ne 0) {
      throw "Strict fixture smoke tests failed."
    }
    Write-Host "[PASS] Strict fixture smoke tests passed."
  }
  catch {
    throw "Strict fixture smoke tests could not be completed. $($_.Exception.Message)"
  }
  finally {
    Pop-Location
  }
}

function Assert-StrictObservabilityArtifacts {
  param(
    [string]$RepoRoot
  )

  $requiredFiles = @(
    (Join-Path $RepoRoot "deploy\config\korda-strict-ingestion-dashboard.json"),
    (Join-Path $RepoRoot "deploy\config\korda-strict-validation-alerts.yaml")
  )
  foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
      throw "Missing strict observability artifact: $file"
    }
  }
  Write-Host "[PASS] Strict observability artifacts present."
}

function Invoke-EnvironmentVerification {
  param(
    [string]$EnvironmentName,
    [hashtable]$Config
  )

  Write-Host ""
  Write-Host "=== Verifying $EnvironmentName ($($Config.PromotionGate)) ==="
  Assert-OverlayControl -OverlayPath $Config.Overlay -EnvironmentName $EnvironmentName
  if ($EnvironmentName -in @("stage", "prod")) {
    Assert-StrictObservabilityArtifacts -RepoRoot $repoRoot
  }

  & (Join-Path $scriptDir "verify-promotion-gate.ps1") `
    -Namespace $Config.Namespace `
    -RagBaseUrl $RagBaseUrl `
    -IngestorBaseUrl $IngestorBaseUrl
  if ($LASTEXITCODE -ne 0) {
    throw "Promotion gate checks failed for $EnvironmentName."
  }

  & (Join-Path $scriptDir "smoke-query.ps1") `
    -RagBaseUrl $RagBaseUrl `
    -CollectionName $CollectionName `
    -Question "Provide a short retrieval and generation smoke validation response."
  if ($LASTEXITCODE -ne 0) {
    throw "Smoke query checks failed for $EnvironmentName."
  }

  Invoke-StrictFixtureSmokeTests -RepoRoot $repoRoot
  Write-Host "[PASS] $EnvironmentName verification completed."
}

$targets = @()
if ($Environment -eq "all") {
  $targets = @("dev", "stage", "prod")
}
else {
  $targets = @($Environment)
}

$failed = @()
foreach ($target in $targets) {
  try {
    Invoke-EnvironmentVerification -EnvironmentName $target -Config $envMatrix[$target]
  }
  catch {
    $failed += "${target}: $($_.Exception.Message)"
  }
}

Write-Host ""
if ($failed.Count -gt 0) {
  Write-Host "Environment verification failures:" -ForegroundColor Red
  $failed | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
  exit 1
}

Write-Host "All requested environment verifications passed." -ForegroundColor Green
