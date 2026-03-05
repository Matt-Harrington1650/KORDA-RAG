param(
  [ValidateSet("prereq", "configure", "rebuild", "deploy", "health", "demo", "verify", "cleanup", "all", "full-demo", "full-verify")]
  [string]$Action = "all",

  [string]$Distro = "",
  [string]$NgcApiKey = "",
  [string]$CollectionName = "multimodal_data",
  [string]$RagBaseUrl = "http://localhost:8081/v1",
  [string]$IngestorBaseUrl = "http://localhost:8082/v1",
  [string]$MilvusEndpoint = "http://milvus:19530",
  [string]$ReportFile = "",
  [int]$DemoTimeoutSeconds = 240,

  [switch]$EnableSaveToDisk,
  [switch]$EnableRagThinking,
  [switch]$EnableVlmInference,
  [switch]$EnableVlmThinking,
  [switch]$StrictProfile,
  [switch]$SkipDockerLogin,
  [switch]$SkipNims,
  [switch]$CpuVectordb,
  [switch]$SkipStrictNegative,
  [switch]$SkipRestartPersistence,
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
    throw "Unable to list WSL distributions. Output: $formatted"
  }

  $rows = @()
  foreach ($line in $raw) {
    $cleanLine = ("$line" -replace "`0", "").TrimEnd()
    if ($cleanLine -match '^\s*\*?\s*(?<name>.+?)\s+(?<state>Running|Stopped)\s+(?<version>\d+)\s*$') {
      $name = $matches["name"].Trim()
      if ($name -and $name -ne "NAME") {
        $rows += [PSCustomObject]@{
          Name      = $name
          State     = $matches["state"]
          Version   = $matches["version"]
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

  throw "Only docker-desktop distros were found. Install a user distro and retry."
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

  & wsl.exe -d $DistroName -- bash -lc "command -v docker >/dev/null 2>&1"
  if ($LASTEXITCODE -ne 0) {
    throw "Docker CLI is not available inside distro '$DistroName'. Enable Docker Desktop WSL integration for this distro and retry."
  }

  & wsl.exe -d $DistroName -- bash -lc "docker compose version >/dev/null 2>&1"
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is not available inside distro '$DistroName'. Ensure Docker Desktop is running and WSL integration is enabled."
  }

  Write-Host "[PASS] Docker CLI and Docker Compose are available in '$DistroName'."
}

Assert-WslAvailable
Assert-DockerDesktopState -SkipCheck:$SkipDockerDesktopCheck

$distroInfo = Resolve-WslDistro -RequestedDistro $Distro
$selectedDistro = $distroInfo.Name
Write-Host "Using WSL distro: $selectedDistro (state: $($distroInfo.State), version: $($distroInfo.Version))"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$repoRootWsl = Convert-WindowsPathToWsl -WindowsPath $repoRoot
$scriptPathWin = Join-Path $repoRoot "scripts\cloud\nvidia-rag-blueprint-quickstart.sh"
$scriptPathWsl = "$repoRootWsl/scripts/cloud/nvidia-rag-blueprint-quickstart.sh"

if (-not (Test-Path $scriptPathWin)) {
  throw "Required script missing: $scriptPathWin"
}

Assert-WslDockerReady -DistroName $selectedDistro

$args = @()
$args += $Action
$args += "--collection-name"
$args += $CollectionName
$args += "--rag-base-url"
$args += $RagBaseUrl
$args += "--ingestor-base-url"
$args += $IngestorBaseUrl
$args += "--milvus-endpoint"
$args += $MilvusEndpoint
$args += "--demo-timeout-seconds"
$args += "$DemoTimeoutSeconds"

if ($EnableSaveToDisk) { $args += "--enable-save-to-disk" }
if ($EnableRagThinking) { $args += "--enable-rag-thinking" }
if ($EnableVlmInference) { $args += "--enable-vlm-inference" }
if ($EnableVlmThinking) { $args += "--enable-vlm-thinking" }
if ($StrictProfile) { $args += "--strict-profile" }
if ($SkipDockerLogin) { $args += "--skip-docker-login" }
if ($SkipNims) { $args += "--skip-nims" }
if ($CpuVectordb) { $args += "--cpu-vectordb" }
if ($ReportFile) {
  $args += "--report-file"
  $args += $ReportFile
}
if ($SkipStrictNegative) { $args += "--skip-strict-negative" }
if ($SkipRestartPersistence) { $args += "--skip-restart-persistence" }

if ($NgcApiKey) {
  $args += "--ngc-api-key"
  $args += $NgcApiKey
}
elseif ($env:NGC_API_KEY) {
  $args += "--ngc-api-key"
  $args += $env:NGC_API_KEY
}

$escapedArgs = @()
foreach ($arg in $args) {
  $escaped = Escape-BashSingleQuotes -Value $arg
  $escapedArgs += "'$escaped'"
}
$argString = $escapedArgs -join " "

$cmd = "cd '$repoRootWsl'; bash '$scriptPathWsl' $argString"
Invoke-WslBash -DistroName $selectedDistro -Command $cmd

Write-Host "Completed action: $Action"
