# Full Scrapy crawl for mediapark, texnomart, uzum with HTTP delivery to local fake-crm-lab.
# Prerequisites: fake-crm-lab at ..\fake-crm-lab, docker compose up, DB migrated.
# Logs: logs/full_crawl_<timestamp>.log
# External tools (python/scrapy) write warnings to stderr; do not treat as terminating.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $LogDir "full_crawl_$Stamp.log"

$env:CRM_BASE_URL = "http://127.0.0.1:8100"
$env:CRM_PARSER_KEY = "dev-parser-key-change-me"
$env:ENABLE_LOCALHOST_BLOCK = "false"
$env:ENABLE_PRIVATE_IP_BLOCK = "false"
$env:MOSCRAPER_DISABLE_PUBLISH = "0"
$env:DEV_MODE = "false"
$env:TRANSPORT_TYPE = "crm_http"

function Write-Log([string]$Msg) {
    $line = "$(Get-Date -Format o) $Msg"
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding utf8
}

Write-Log "=== full_crawl_all_stores_fake_crm start (no CLOSESPIDER_ITEMCOUNT, crawl until queues empty) ==="
Write-Log "CRM UI: http://127.0.0.1:8100/ui"
Write-Log "Log file: $Log"

Push-Location $Root
try {
    foreach ($store in @("mediapark", "texnomart", "uzum")) {
        Write-Log "---------- START spider=$store ----------"
        & python -m scrapy crawl $store -s LOG_LEVEL=INFO 2>&1 | Tee-Object -FilePath $Log -Append
        $code = $LASTEXITCODE
        Write-Log "---------- END spider=$store exit=$code ----------"
        if ($code -ne 0) {
            Write-Log "Spider $store exited with $code; continuing with next store."
        }
    }
} finally {
    Pop-Location
}
Write-Log "=== full_crawl_all_stores_fake_crm finished ==="
