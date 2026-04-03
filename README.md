# Moscraper

Scrapy-based ingestion service for Uzbekistan e-commerce stores. The active delivery boundary is now:

`Store Spider -> structured raw item -> Scraper DB -> outbox -> Publisher Service -> RabbitMQ`

- **Config reference:** [.env.example](.env.example) (copy to `.env`; loaded by `pydantic-settings`)
- **Doc index:** [docs/README.md](docs/README.md)
- **Commands & DX:** [DEV_WORKFLOW.md](DEV_WORKFLOW.md)

## Current architecture (short)

- **Scrapy** spiders under `infrastructure/spiders/`; store lists driven by `STORE_NAMES` / settings.
- **Scraper pipeline:** validate item → persist snapshot into local scraper DB → enqueue outbox row.
- **Publisher service:** reads unpublished outbox rows and publishes contract events to RabbitMQ with safe retry.
- **Scraper DB:** keeps scrape runs, product snapshots, outbox state, and publication attempts for replay/debug/export.
- **Normalization/CRM code:** still exists in the repo as legacy material, but the active runtime path is the scraper DB/outbox publisher contour.

## Quick setup

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Unix/macOS:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`: set `SCRAPER_DB_PATH`, `RABBITMQ_URL`, `RABBITMQ_EXCHANGE`, `RABBITMQ_QUEUE`, and `RABBITMQ_ROUTING_KEY` for your local environment. `TRANSPORT_TYPE` should stay `disabled` for the active scraper contour; CRM settings remain legacy-only and are not part of the scraper-to-publisher runtime.

## Single-store run

```powershell
python -m scrapy list
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5
```

## Publisher service

Run the standalone outbox publisher once:

```powershell
python -m services.publisher.main --once
```

Run it continuously:

```powershell
python -m services.publisher.main
```

## Local smoke & readiness

```powershell
python scripts/local_smoke.py
python scripts/check_readiness.py
```

## Optional browser-backed stores

Some spiders use Playwright via per-spider `custom_settings`:

```powershell
pip install -e ".[playwright]"
playwright install
```

## Testing

```powershell
python -m pytest tests/unit -q
python -m pytest tests/contracts -q --tb=no
python -m pytest tests/acceptance -q
```

## Documentation index

| Doc | Purpose |
|-----|---------|
| [docs/README.md](docs/README.md) | Full navigation index (ADRs, stores, governance). |
| [DEV_WORKFLOW.md](DEV_WORKFLOW.md) | Fixture replay, debug summaries, gate snippets. |
| [docs/onboarding.md](docs/onboarding.md) | First-day orientation and safe-change rules. |
| [docs/crm_integration.md](docs/crm_integration.md) | Sync, batch, lifecycle, CRM-facing contract. |
| [docs/support_triage.md](docs/support_triage.md) | Health, triage, runbooks, safe exports. |
| [docs/release_process.md](docs/release_process.md) | Gates, rollout, compatibility. |
| [docs/production_readiness.md](docs/production_readiness.md) | Readiness domains, evidence, `check_readiness.py`. |
| [PROJECT.md](PROJECT.md) | Non-negotiable architecture and boundaries. |

## Delivery boundary

- **Required boundary:** RabbitMQ. The scraper side owns data until it is durably stored in scraper DB and successfully published from outbox to RabbitMQ.
- **Not in scope for this service:** CRM writes, deep canonical matching, multi-store merge, or final downstream normalization.
