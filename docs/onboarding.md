# Onboarding

## What this project is

**Moscraper** is a **stateless** Scrapy parser: scrape → validate → normalize → sync (CRM HTTP or broker per config). No parser-owned DB of listings. CRM owns dedup, full normalization, and long-term storage. See [`PROJECT.md`](../PROJECT.md).

## Run locally

- Python venv, `pip install -e ".[dev]"` (or project’s documented extras).
- Copy [`.env.example`](../.env.example) → `.env`; set `CRM_*` as needed for real CRM, or use **dry-run** (below).

## Dry-run (no real CRM HTTP)

Set `DEV_MODE=true`, `TRANSPORT_TYPE=crm_http`, `DEV_DRY_RUN_DISABLE_CRM_SEND=true`, `MOSCRAPER_DISABLE_PUBLISH=false`. Pipeline still builds lifecycle/apply simulation; transport does not call CRM. Details: [`DEV_WORKFLOW.md`](../DEV_WORKFLOW.md).

## One store / one spider

```bash
python -m scrapy list
python -m scrapy crawl <spider_name> -s CLOSESPIDER_ITEMCOUNT=5
```

Validate store name: `python scripts/dev_run.py resolve <store>`.

## Normalized / lifecycle / debug output

With `DEV_MODE` and debug summaries enabled, logs include compact `dx_event` / `parser_dx_v1` previews. Use fixture replay for offline inspection: `application.dev.fixture_replay`. See [`DEV_WORKFLOW.md`](../DEV_WORKFLOW.md).

## Reproduce a bug via fixtures

1. Find or add JSON under `tests/fixtures/`.
2. `replay_normalization_fixture` / `replay_lifecycle_fixture` from `application.dev.fixture_replay` (no CRM).

## Where logic lives

| Topic | Location |
|--------|-----------|
| Spiders | `infrastructure/spiders/` |
| Validate | `infrastructure/pipelines/validate_pipeline.py` |
| Normalize | `infrastructure/pipelines/normalize_pipeline.py`, `application/extractors/` |
| Lifecycle | `application/lifecycle/` |
| Sync / transport | `infrastructure/pipelines/sync_pipeline.py`, `infrastructure/transports/` |
| Observability | `infrastructure/observability/` |
| Security | `infrastructure/security/` |
| Release gates | `application/release/release_gate_evaluator.py` |

## Docs order (recommended)

1. [`PROJECT.md`](../PROJECT.md)  
2. [`docs/README.md`](README.md) (this index)  
3. [`OWNERSHIP_MAP.md`](../OWNERSHIP_MAP.md)  
4. [`docs/crm_integration.md`](crm_integration.md)  
5. Relevant [`docs/adr/`](adr/README.md)  
6. Store playbook: [`docs/stores/<store>.md`](stores/mediapark.md)

## Do not change lightly (without gates / rollout / compatibility)

- Default lifecycle event and delta feature flags (`PARSER_*`, `CRM_*` sync semantics).
- `entity_key`, `payload_hash`, idempotency/replay contracts.
- Transport endpoints, signing, security modes.
- Store rollout stages and release gate inputs.
- Contract tests and regression fixtures for enabled stores.

When in doubt: run contract + unit tests, check [`docs/release_process.md`](release_process.md), and update ADRs / store playbooks if behavior changes.
