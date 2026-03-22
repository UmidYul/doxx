# Moscraper test strategy (parser → CRM)

Formal taxonomy for **production-ready** validation: correctness, **contract stability**, replay safety, observability, and store acceptance — without relying on a hosted CI product in this repo.

## unit

| | |
|---|---|
| **Goal** | Fast, isolated verification of pure logic (normalizers, lifecycle rules, hash/idempotency, classifiers). |
| **Covers** | Deterministic functions, Pydantic models, small pipelines with mocks. |
| **Does not cover** | Real HTTP, real brokers, full Scrapy crawls, cross-service timing. |
| **When mandatory** | Every change touching `domain/`, `application/` algorithms, or transport adapters. |
| **Artifacts** | Pytest, local venv; no network by default. |

## contract

| | |
|---|---|
| **Goal** | Prevent **silent drift** of CRM-facing JSON shapes (sync payload, lifecycle envelope, batch apply, ETL export, diagnostics). |
| **Covers** | Required keys, stable types, schema version fields; optional expansion allowed. |
| **Does not cover** | Business outcome in CRM DB, full message equality (timestamps, UUIDs). |
| **When mandatory** | **Release gate** — any change to `domain/crm_sync.py`, `domain/parser_event.py`, `domain/messages.py`, `domain/crm_apply_result.py`, ETL exporter schemas. |
| **Artifacts** | `tests/contracts/`, `tests/helpers/builders.py`, normalized snapshots (no volatile fields). |

## component

| | |
|---|---|
| **Goal** | Several units wired together (e.g. normalize → CRM sync builder → event) with mocks for IO. |
| **Covers** | Pipeline stages inside the parser process, batch coordinator behavior. |
| **Does not cover** | Live store HTML, production CRM. |
| **When mandatory** | Changes to `sync_pipeline`, `normalize_pipeline`, batch apply path. |
| **Artifacts** | `tests/unit/` integration-style tests with `MagicMock` / fake transport. |

## acceptance

| | |
|---|---|
| **Goal** | **Store-quality** guarantees on **fixture HTML** (listing/PDP/shell) per store profile. |
| **Covers** | Extractors + field policy + QA gates for registered stores (`mediapark`, `uzum`, …). |
| **Does not cover** | Live site scraping in default CI (see canary/integration opt-in). |
| **When mandatory** | **Release gate** for every **enabled** store in `STORE_NAMES` that has a runner. |
| **Artifacts** | `tests/fixtures/stores/`, `application/qa/run_store_acceptance.py`, `tests/acceptance/`. |

## regression

| | |
|---|---|
| **Goal** | Guard **golden** normalization/lifecycle/replay behavior so refactors do not regress mapping, suppression, or idempotency. |
| **Covers** | Category fixtures (phone/laptop/tv/appliance), replay journal semantics, batch partial success. |
| **Does not cover** | Auto-downloaded prod pages (explicitly out of scope for 6A). |
| **When mandatory** | **Release gate** for changes to normalization, lifecycle, replay, or CRM apply classification. |
| **Artifacts** | `tests/fixtures/regression/`, `tests/regression/`. |

## release-gate

| | |
|---|---|
| **Goal** | Single **readiness decision**: `release` \| `release_with_caution` \| `block_release` from aggregated checks + gates. |
| **Covers** | Composition of unit/contract/acceptance/regression signals; payload compatibility vs baselines. |
| **Does not cover** | Deployment, k8s, external ticketing. |
| **When mandatory** | Before tagging a production candidate (manual or future CI job invoking pytest + evaluator). |
| **Artifacts** | `application/release/release_gate_evaluator.py`, `application/release/release_summary.py`, `domain/release_quality.py`. |

## Suggested local matrix (no external CI)

1. `pytest tests/unit -q`  
2. `pytest tests/contracts -q`  
3. `pytest tests/acceptance -q`  
4. `pytest tests/regression -q`  
5. Optional: `pytest tests/integration -q` (broker/network)  
6. Interpret `build_release_readiness_summary` / `build_release_report` for go/no-go.
