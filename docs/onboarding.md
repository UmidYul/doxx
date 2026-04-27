# Onboarding

## What this project is

**Moscraper** is now a scraper-side ingestion system with a durable boundary:

`store spider -> Supabase-backed scraper DB -> outbox -> publisher service -> RabbitMQ`

The scraper owns extraction quality, minimal structuring, and durable persistence. It does not own CRM writes, deep normalization, or cross-store merge logic.

## Run locally

- Create a venv and install `pip install -e ".[dev]"`.
- Copy [`.env.example`](../.env.example) to `.env`.
- Set `SCRAPER_DB_BACKEND=postgres`, `SCRAPER_DB_DSN`, `SCRAPER_DB_MIGRATION_DSN`, `RABBITMQ_URL`, `RABBITMQ_MANAGEMENT_URL`, `RABBITMQ_CRM_USER`, and `RABBITMQ_CRM_PASS`.
- Run `python -m scripts.bootstrap_scraper_db` before the first scraper or publisher start in a fresh environment.
- Run `python -m scripts.bootstrap_rabbitmq` before the first publisher or CRM smoke run.
- Keep `TRANSPORT_TYPE=disabled` unless you are explicitly working on legacy CRM-only modules.

## One store / one spider

```bash
python -m scrapy list
python -m scrapy crawl <spider_name> -s CLOSESPIDER_ITEMCOUNT=5
```

This writes into scraper DB and creates outbox rows. It does not publish from spider code.

Validate store name: `python scripts/dev_run.py resolve <store>`.

## Publisher service

Publish pending outbox rows separately:

```bash
python -m services.publisher.main --once
python -m services.publisher.main
```

## Fixture-based checks

- Store acceptance runner: `python -m application.qa.run_store_acceptance`
- Unit and acceptance suites: `python -m pytest tests/unit -q` and `python -m pytest tests/acceptance -q`
- Legacy normalization fixture replay remains in the repo only for migration/debug context; it is not the active ingestion runtime.

## Where logic lives

| Topic | Location |
|--------|-----------|
| Spiders | `infrastructure/spiders/` |
| Validate | `infrastructure/pipelines/validate_pipeline.py` |
| Persistence pipeline | `infrastructure/pipelines/scraper_storage_pipeline.py` |
| Scraper DB | `infrastructure/persistence/postgres_store.py` (`sqlite_store.py` remains as legacy/local fallback) |
| Publisher service | `services/publisher/` |
| Contracts | `shared/contracts/` |
| Observability | `infrastructure/observability/` |
| Security | `infrastructure/security/` |
| Release gates | `application/release/release_gate_evaluator.py` |

## Docs order (recommended)

1. [`PROJECT.md`](../PROJECT.md)
2. [`docs/README.md`](README.md)
3. [`docs/new_scraper_architecture.md`](new_scraper_architecture.md)
4. [`docs/final_ingestion_flow.md`](final_ingestion_flow.md)
5. Store playbook: [`docs/stores/<store>.md`](stores/mediapark.md)
6. [`OWNERSHIP_MAP.md`](../OWNERSHIP_MAP.md)

## Do not change lightly

- the raw product persistence contract
- the outbox schema and publication semantics
- the RabbitMQ event contract
- store-specific listing and PDP extraction behavior for enabled stores
- acceptance fixtures and store playbooks

When in doubt: run unit + acceptance tests, check [`docs/release_process.md`](release_process.md), and update the relevant store playbook and architecture docs together.
