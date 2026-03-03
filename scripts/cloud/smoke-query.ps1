param(
  [string]$RagBaseUrl = "http://localhost:8081/v1",
  [string]$CollectionName = "multimodal_data",
  [string]$Question = "Summarize the key points in this collection."
)

$ErrorActionPreference = "Stop"

$searchBody = @{
  query            = $Question
  collection_names = @($CollectionName)
  enable_reranker  = $true
} | ConvertTo-Json -Depth 8

$generateBody = @{
  messages = @(
    @{
      role    = "user"
      content = $Question
    }
  )
  collection_names = @($CollectionName)
} | ConvertTo-Json -Depth 8

Write-Host "Running search smoke check..."
$searchResp = Invoke-RestMethod -Method Post -Uri "$RagBaseUrl/search" -ContentType "application/json" -Body $searchBody
Write-Host ("Search citations count: " + (($searchResp.citations | Measure-Object).Count))

Write-Host "Running generate smoke check..."
$genResp = Invoke-RestMethod -Method Post -Uri "$RagBaseUrl/generate" -ContentType "application/json" -Body $generateBody

if (-not $genResp.answer -and -not $genResp.choices) {
  throw "Generate response did not include expected answer fields."
}

Write-Host "Smoke query completed successfully."
