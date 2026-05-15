$ErrorActionPreference = 'Stop'
$api = 'http://localhost:8080/health'
$ui = 'http://localhost:3000/api/health'

function Test-Url([string]$name, [string]$url) {
  Write-Host "GET $url"
  $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
  if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 300) {
    throw "$name returned $($r.StatusCode)"
  }
  Write-Host "  -> $($r.StatusCode) $($r.Content.Substring(0, [Math]::Min(200, $r.Content.Length)))"
}

Test-Url 'go-api' $api
Test-Url 'ts-ui /api proxy' $ui
Write-Host 'verify-stack: OK'
