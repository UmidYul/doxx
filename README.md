# Moscraper

Stateless Scrapy **parser** for Uzbekistan e‑commerce stores. Data leaves the process after **validation → normalization → lifecycle** and **sync to CRM** over **HTTP** (primary). Optional **RabbitMQ** remains a **legacy / alternate** transport when enabled.

- **Config reference:** [.env.example](.env.example) (copy to `.env`; loaded by `pydantic-settings`)
- **Doc index:** [docs/README.md](docs/README.md)
- **Commands & DX:** [DEV_WORKFLOW.md](DEV_WORKFLOW.md)

## Current architecture (short)

- **Scrapy** spiders under `infrastructure/spiders/`; store lists driven by `STORE_NAMES` / settings.
- **Domain** rules stay free of infrastructure imports (`domain/`).
- **Pipeline:** extract → normalize → lifecycle events → **CRM HTTP** batch/sync (default `TRANSPORT_TYPE=crm_http`).
- **Outbound data:** structured logs, metrics, optional ETL-style status export — **no** scraper-owned DB or listing backlog (see [PROJECT.md](PROJECT.md)).
- **RabbitMQ:** only if you set `TRANSPORT_TYPE=rabbitmq` — not the default developer path.

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

Edit `.env`: set `CRM_BASE_URL` / `CRM_PARSER_KEY` when exercising real CRM (see comments in `.env.example`). For local exploration, use dry-run below.

## Single-store run

```powershell
python -m scrapy list
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5
```

## Dry-run (no real CRM HTTP)

Keep **`TRANSPORT_TYPE=crm_http`** (default). Enable dev mode and dry-run (env or `.env`):

```powershell
$env:DEV_MODE="true"
$env:DEV_DRY_RUN_DISABLE_CRM_SEND="true"
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=3
```

`DEV_DRY_RUN_DISABLE_CRM_SEND` is honored **with** `DEV_MODE=true` (see `DEV_WORKFLOW.md`).

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

## Legacy / optional transport (RabbitMQ)

- **Default path:** CRM HTTP (`TRANSPORT_TYPE=crm_http` in `.env.example`).
- **Legacy path:** set `TRANSPORT_TYPE=rabbitmq` and configure `RABBITMQ_*` per `.env.example` if you still publish CloudEvents to a broker instead of (or in addition to) CRM — this is **not** the primary operator/developer workflow today.
- Do not assume `docker compose up -d` for RabbitMQ unless you intentionally use that transport.
