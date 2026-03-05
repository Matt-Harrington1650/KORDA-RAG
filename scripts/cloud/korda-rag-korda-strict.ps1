param(
  [ValidateSet("start", "verify", "stop", "all")]
  [string]$Action = "all",

  [string]$Distro = "",
  [string]$NgcApiKey = "",
  [string]$RagBaseUrl = "http://localhost:8081/v1",
  [string]$IngestorBaseUrl = "http://localhost:8082/v1",
  [string]$CollectionName = "multimodal_data",
  [switch]$SkipDockerDesktopCheck
)

$ErrorActionPreference = "Stop"

function Convert-WindowsPathToWsl {
  param([string]$WindowsPath)

  if ($WindowsPath -match '^([A-Za-z]):\\(.*)$') {
    $drive = $matches[1].ToLower()
    $rest = $matches[2] -replace '\\', '/'
    return "/mnt/$drive/$rest"
  }
  throw "Unsupported Windows path format for WSL conversion: $WindowsPath"
}

function Escape-BashSingleQuotes {
  param([string]$Value)
  $replacement = "'" + '"' + "'" + '"' + "'"
  return $Value.Replace("'", $replacement)
}

function Assert-WslAvailable {
  if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe was not found. Install WSL and a Linux distro first."
  }
}

function Format-WslCommandOutput {
  param([object[]]$RawLines)

  $cleanLines = @()
  foreach ($entry in $RawLines) {
    $cleanLines += ("$entry" -replace "`0", "").TrimEnd()
  }
  return ($cleanLines -join [Environment]::NewLine).Trim()
}

function Get-WslDistroTable {
  $raw = & wsl.exe -l -v 2>&1
  if ($LASTEXITCODE -ne 0) {
    $formatted = Format-WslCommandOutput -RawLines $raw
    if ($formatted -match "E_ACCESSDENIED|Access is denied") {
      throw "WSL access denied while listing distributions. Ensure WSL is enabled for your user and retry (elevated terminal may be required). Raw output: $formatted"
    }
    throw "Unable to list WSL distributions. Output: $formatted"
  }

  $rows = @()
  foreach ($line in $raw) {
    $cleanLine = ("$line" -replace "`0", "").TrimEnd()
    if ($cleanLine -match '^\s*\*?\s*(?<name>.+?)\s+(?<state>Running|Stopped)\s+(?<version>\d+)\s*$') {
      $name = $matches["name"].Trim()
      if ($name -and $name -ne "NAME") {
        $rows += [PSCustomObject]@{
          Name = $name
          State = $matches["state"]
          Version = $matches["version"]
          IsDefault = $cleanLine.TrimStart().StartsWith("*")
        }
      }
    }
  }

  if ($rows.Count -eq 0) {
    throw "No WSL distributions found. Install a distro (for example Ubuntu) and retry."
  }

  return $rows
}

function Resolve-WslDistro {
  param([string]$RequestedDistro)

  $rows = Get-WslDistroTable

  if ($RequestedDistro) {
    $match = $rows | Where-Object { $_.Name -eq $RequestedDistro } | Select-Object -First 1
    if (-not $match) {
      $available = ($rows | ForEach-Object { $_.Name }) -join ", "
      throw "Requested distro '$RequestedDistro' not found. Available distros: $available"
    }
    return $match
  }

  $default = $rows | Where-Object { $_.IsDefault } | Select-Object -First 1
  if ($default -and $default.Name -notin @("docker-desktop", "docker-desktop-data")) {
    return $default
  }

  $preferred = $rows | Where-Object { $_.Name -notin @("docker-desktop", "docker-desktop-data") } | Select-Object -First 1
  if ($preferred) {
    return $preferred
  }

  throw "Only docker-desktop distros were found. Install a user distro (for example Ubuntu) and retry."
}

function Assert-DockerDesktopState {
  param([switch]$SkipCheck)

  if ($SkipCheck) {
    Write-Host "[SKIP] Docker Desktop service check disabled."
    return
  }

  $svc = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
  if (-not $svc) {
    Write-Host "[WARN] com.docker.service not found. Continuing without Docker Desktop service validation."
    return
  }

  if ($svc.Status -ne "Running") {
    throw "Docker Desktop service (com.docker.service) is not running. Start Docker Desktop and retry."
  }

  Write-Host "[PASS] Docker Desktop service is running."
}

function Invoke-WslBash {
  param(
    [string]$DistroName,
    [string]$Command
  )

  & wsl.exe -d $DistroName -- bash -lc $Command
  if ($LASTEXITCODE -ne 0) {
    throw "WSL command failed in distro '$DistroName'. Command: $Command"
  }
}

function Assert-WslDockerReady {
  param([string]$DistroName)

  Invoke-WslBash -DistroName $DistroName -Command "command -v docker >/dev/null 2>&1"
  Invoke-WslBash -DistroName $DistroName -Command "docker compose version >/dev/null 2>&1"
  Write-Host "[PASS] Docker CLI and Docker Compose are available in '$DistroName'."
}

Assert-WslAvailable
Assert-DockerDesktopState -SkipCheck:$SkipDockerDesktopCheck

$distroInfo = Resolve-WslDistro -RequestedDistro $Distro
$selectedDistro = $distroInfo.Name
Write-Host "Using WSL distro: $selectedDistro (state: $($distroInfo.State), version: $($distroInfo.Version))"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$repoRootWsl = Convert-WindowsPathToWsl -WindowsPath $repoRoot

$startScriptWin = Join-Path $repoRoot "scripts\cloud\run-korda-rag-korda-strict.sh"
$verifyScriptWin = Join-Path $repoRoot "scripts\cloud\verify-korda-rag-korda-strict.sh"
$stopScriptWin = Join-Path $repoRoot "scripts\cloud\shutdown-korda-rag-korda-strict.sh"

foreach ($scriptPath in @($startScriptWin, $verifyScriptWin, $stopScriptWin)) {
  if (-not (Test-Path $scriptPath)) {
    throw "Required script is missing: $scriptPath"
  }
}

$startScriptWsl = "$repoRootWsl/scripts/cloud/run-korda-rag-korda-strict.sh"
$verifyScriptWsl = "$repoRootWsl/scripts/cloud/verify-korda-rag-korda-strict.sh"
$stopScriptWsl = "$repoRootWsl/scripts/cloud/shutdown-korda-rag-korda-strict.sh"

Assert-WslDockerReady -DistroName $selectedDistro

$effectiveApiKey = $NgcApiKey
if (-not $effectiveApiKey) {
  $effectiveApiKey = $env:NGC_API_KEY
}

function Start-KordaRagStrict {
  if (-not $effectiveApiKey) {
    throw "NGC API key is required for startup. Use -NgcApiKey or set NGC_API_KEY in PowerShell session."
  }

  $key = Escape-BashSingleQuotes -Value $effectiveApiKey
  $cmd = "export NGC_API_KEY='$key'; export NVIDIA_API_KEY='$key'; bash '$startScriptWsl'"
  Invoke-WslBash -DistroName $selectedDistro -Command $cmd
}

function Verify-KordaRagStrict {
  $rag = Escape-BashSingleQuotes -Value $RagBaseUrl
  $ing = Escape-BashSingleQuotes -Value $IngestorBaseUrl
  $col = Escape-BashSingleQuotes -Value $CollectionName
  $cmd = "export RAG_BASE_URL='$rag'; export INGESTOR_BASE_URL='$ing'; export COLLECTION_NAME='$col'; bash '$verifyScriptWsl'"
  Invoke-WslBash -DistroName $selectedDistro -Command $cmd
}

function Stop-KordaRagStrict {
  Invoke-WslBash -DistroName $selectedDistro -Command "bash '$stopScriptWsl'"
}

switch ($Action) {
  "start" {
    Start-KordaRagStrict
  }
  "verify" {
    Verify-KordaRagStrict
  }
  "stop" {
    Stop-KordaRagStrict
  }
  "all" {
    Start-KordaRagStrict
    Verify-KordaRagStrict
  }
}

Write-Host "Completed action: $Action"
