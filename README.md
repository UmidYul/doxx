# Moscraper

Scrapy-based ingestion service for Uzbekistan e-commerce stores.

Active runtime boundary:

`Store Spider -> structured raw item -> Supabase-backed Scraper DB -> outbox -> Publisher Service -> RabbitMQ`

- Config reference: [.env.example](.env.example)
- Doc index: [docs/README.md](docs/README.md)
- Commands and DX: [DEV_WORKFLOW.md](DEV_WORKFLOW.md)

## Current architecture

- Scrapy spiders live under `infrastructure/spiders/`.
- The scraper runtime persists each item into Postgres tables under the `scraper` schema and refreshes one durable outbox row per raw product.
- The standalone publisher claims outbox rows, publishes `scraper.product.scraped.v1` to RabbitMQ, and records publication attempts.
- CRM remains downstream of RabbitMQ and continues to consume from `crm.products.import.v1`.

## Quick setup

Windows:

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

Set these before runtime:

- `SCRAPER_DB_BACKEND=postgres`
- `SCRAPER_DB_DSN`
- `SCRAPER_DB_MIGRATION_DSN`
- `RABBITMQ_URL`
- `RABBITMQ_MANAGEMENT_URL`
- `RABBITMQ_CRM_USER` / `RABBITMQ_CRM_PASS`

Keep `RABBITMQ_DECLARE_TOPOLOGY=false` in the hardened stack. `TRANSPORT_TYPE` stays `disabled` for the active scraper contour.

## Bootstrap

Apply the Postgres schema/bootstrap SQL:

```powershell
python -m scripts.bootstrap_scraper_db
```

Bootstrap RabbitMQ topology:

```powershell
python -m scripts.bootstrap_rabbitmq
```

## Single-store run

```powershell
python -m scrapy list
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5
```

## Operator UI

Run the local scraper operator UI:

```powershell
python -m services.ui_api.main --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The UI covers the narrow scraper workflow: choose a store, optionally limit the run to a category/brand/category URL, set custom time and/or item limits, optionally set a custom parse interval in seconds, start a run, watch live logs, stop a run, read the short summary, and publish pending outbox rows to RabbitMQ on demand. Russian is the default UI language; Uzbek can be selected in the top bar. It intentionally does not manage outbox replay, CRM cutover, exports, or RabbitMQ queues.

## Publisher service

Publish one batch and exit:

```powershell
python -m services.publisher.main --once
```

Run continuously:

```powershell
python -m services.publisher.main
```

Replay already-saved rows back into the outbox:

```powershell
python -m scripts.replay_outbox --store mediapark --status published --limit 50
```

## Docker / VPS

For the hosted deployment contour:

```powershell
docker compose -f docker-compose.cloud.yml up --build publisher
docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl mediapark
```

- `publisher` is the only always-on app service.
- `scraper-job` is meant for host cron or manual one-shot runs.
- `scraper-db-bootstrap` applies the Postgres schema before app services start.

## Local smoke & readiness

```powershell
python -m scripts.rabbit_smoke
python scripts/local_smoke.py
python scripts/check_readiness.py
```

## Optional browser-backed stores

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

Postgres-backed tests require a DSN in `MOSCRAPER_TEST_POSTGRES_DSN`.

## Documentation index

| Doc | Purpose |
|-----|---------|
| [docs/README.md](docs/README.md) | Full navigation index. |
| [docs/supabase_deployment.md](docs/supabase_deployment.md) | Supabase DSNs, managed RabbitMQ, cron-run scraper jobs, replay operations. |
| [docs/onboarding.md](docs/onboarding.md) | First-day orientation and safe-change rules. |
| [docs/crm_integration.md](docs/crm_integration.md) | CRM-facing contract and integration notes. |
| [docs/support_triage.md](docs/support_triage.md) | Health, triage, runbooks, safe exports. |
| [docs/release_process.md](docs/release_process.md) | Gates, rollout, compatibility. |
| [docs/production_readiness.md](docs/production_readiness.md) | Readiness domains and evidence. |
| [PROJECT.md](PROJECT.md) | Core architecture boundaries. |

## Delivery boundary

- Required boundary: RabbitMQ.
- The scraper side owns data until it is durably stored in the scraper DB and successfully published from outbox to RabbitMQ.
- Not in scope for this service: CRM writes, deep canonical matching, multi-store merge, or final downstream normalization.
