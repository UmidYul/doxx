# Start fake-crm-lab (sibling repo) and run a short Scrapy crawl with CRM HTTP delivery.
# Prerequisite: https://github.com/... fake-crm-lab at ..\fake-crm-lab (see README in that repo).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Lab = Join-Path (Split-Path -Parent $Root) "fake-crm-lab"
if (-not (Test-Path (Join-Path $Lab "docker-compose.yml"))) {
    Write-Error "Expected fake-crm-lab at: $Lab"
}
Push-Location $Lab
docker compose up -d --build
docker compose exec -T app alembic upgrade head
Pop-Location

$env:CRM_BASE_URL = "http://127.0.0.1:8100"
$env:CRM_PARSER_KEY = "dev-parser-key-change-me"
$env:ENABLE_LOCALHOST_BLOCK = "false"
$env:ENABLE_PRIVATE_IP_BLOCK = "false"
$env:MOSCRAPER_DISABLE_PUBLISH = "0"
$env:DEV_MODE = "false"
$env:TRANSPORT_TYPE = "crm_http"
$env:STORE_NAMES = '["mediapark","texnomart","uzum"]'

$store = if ($args[0]) { $args[0] } else { "mediapark" }
$items = if ($args[1]) { $args[1] } else { "10" }

Push-Location $Root
python -m scrapy crawl $store -s "CLOSESPIDER_ITEMCOUNT=$items" -s CLOSESPIDER_TIMEOUT=240 -s LOG_LEVEL=INFO
Pop-Location

Write-Host ""
Write-Host "CRM UI: http://127.0.0.1:8100/ui"
Write-Host "Health: http://127.0.0.1:8100/status/health"
