# Moscraper architecture map (9A)

This document fixes **layer boundaries** and **dependency direction** so new work lands in the right module. It complements `PROJECT.md` (product/stateless rules).

## Layers

### `config/`

- **Allowed:** Pydantic `Settings`, Scrapy settings dict wiring, env parsing, thin imports from `domain/` (types) and minimal `infrastructure/` (e.g. proxy policy for handlers).
- **Forbidden:** Business orchestration, spiders, transports, CRM batching, normalization pipelines.
- **May depend on:** `config`, `domain`, `infrastructure` (glue only).
- **Typical logic:** feature flags as fields, timeouts, URLs, Scrapy `DOWNLOAD_HANDLERS` wiring.

### `domain/`

- **Allowed:** Pydantic models, enums, value objects, stable contracts (`RawProduct`, events, CRM apply DTOs).
- **Forbidden:** Scrapy, HTTP clients, RabbitMQ, SQL, imports from `application/` or `infrastructure/`.
- **May depend on:** `domain` only.
- **Typical logic:** schema versions, keys, hashes, lifecycle enums—no I/O.

### `application/`

- **Allowed:** Use-cases, policies, orchestration, lifecycle selection, normalization rules, extractors/registries, release/rollout, QA harnesses, governance (9A).
- **Forbidden:** Direct Scrapy spider classes, raw HTTP to stores (except tests), importing `tests/` or `scripts/`.
- **May depend on:** `config`, `domain`, `application`, `infrastructure` (thin adapters: logging, metrics, optional store acceptance helpers).
- **Typical logic:** “what event to emit”, “how to map specs”, compatibility checks—not raw HTML scraping.

### `infrastructure/`

- **Allowed:** Spiders, pipelines, middlewares, transports, security, observability, performance collectors, sync runtime bridges.
- **Forbidden:** Declaring CRM business rules that belong in CRM; long-lived listing databases.
- **May depend on:** `config`, `domain`, `application`, `infrastructure`.
- **Typical logic:** I/O, scheduling requests, publishing, redaction, metrics—**adapters**.

### `tests/`

- **Allowed:** Pytest suites, fixtures, contract tests, golden files, mocks.
- **Forbidden:** Production entrypoints only; do not ship test helpers as runtime defaults.
- **May depend on:** all production layers for verification.

### `scripts/`

- **Allowed:** One-off maintenance, CI helpers, local tooling.
- **Forbidden:** Imported by runtime spiders/pipelines in production paths.
- **May depend on:** production code as needed; **not** `tests/`.

## Dependency direction (summary)

```
scripts, tests  →  (may import)  →  infrastructure, application, domain, config
infrastructure  →  application, domain, config
application     →  infrastructure (thin), domain, config
domain          →  domain
config          →  infrastructure (glue), domain
```

## Placement quick reference

| Concern | Layer |
|--------|--------|
| Store HTML/JSON extraction | `infrastructure/spiders/` |
| Access / proxy / browser policy | `infrastructure/access/` |
| Normalization & spec mapping | `application/normalization/`, `application/extractors/` |
| Lifecycle & replay | `application/lifecycle/` |
| CRM HTTP / sync delivery | `infrastructure/transports/`, `infrastructure/pipelines/` |
| Security & redaction | `infrastructure/security/` |
| Observability codes | `infrastructure/observability/` |
| Release gates | `application/release/` |
| Contracts | `domain/` |

See also `application/governance/code_placement.py` and `CODE_STANDARDS.md`.
