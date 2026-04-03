# New Scraper Architecture

## Scope

This document is the **stage 1** architecture blueprint for rebuilding `doxx` into a production-like scraper contour with a hard boundary at RabbitMQ:

`Scraper Service -> Scraper DB -> Publisher Service -> RabbitMQ`

This stage does **not** include:

- full store migration
- full publisher hardening
- CRM-side business logic
- deep normalization
- cross-store product merge

It defines the foundation that those later stages must build on.

## Current `doxx` analysis

### Keep

These parts are still useful and should survive the rewrite:

- `infrastructure/spiders/base.py`
  Good crawl framework for listing traversal, pagination guards, dedupe, and acceptance integration.
- `infrastructure/spiders/field_policy.py`
  Still useful as pre-persistence quality gating for minimal required fields.
- `infrastructure/spiders/url_tools.py`
  Canonical URL helpers still belong in the scraping layer.
- `infrastructure/spiders/runtime_crawl_registry.py`
  Useful for crawl-local dedupe and diagnostics.
- `infrastructure/access/`, `infrastructure/middlewares/`, `infrastructure/security/`
  The anti-bot, request strategy, proxy/browser escalation, and outbound safety layers remain relevant.
- `tests/fixtures/stores/` and `tests/acceptance/test_store_acceptance.py`
  These are valuable for store migration safety and fixture-based acceptance.
- `infrastructure/spiders/product_classifier.py`
  Only as a **light hinting helper** for `brand` / `category_hint`, not as deep normalization.

### Remove from active runtime

These components should no longer sit on the critical scrape path:

- `infrastructure/pipelines/normalize_pipeline.py`
- `infrastructure/pipelines/sync_pipeline.py`
- `infrastructure/pipelines/publish_pipeline.py`
- `infrastructure/transports/crm_http.py`
- `infrastructure/transports/rabbitmq.py`
- `infrastructure/transports/factory.py`
- `application/crm_sync_builder.py`
- `application/message_builder.py`
- `application/lifecycle/`
- `domain/crm_sync.py`
- `domain/crm_apply_result.py`
- `domain/crm_lifecycle.py`
- `domain/parser_event.py`
- `domain/normalized_product.py`

These modules do not need to be physically deleted in stage 1, but they must be **weakened into legacy-only code** and removed from the active scraper runtime.

### Rewrite by `E-katalog` reference

- `infrastructure/spiders/mediapark.py`
  Must be rewritten closest to the old `E-katalog` MediaPark parser. This is the highest-priority store.
- `infrastructure/spiders/texnomart.py`
  Should be rewritten using the old `E-katalog` Texnomart parsing approach.
- `alifshop`
  Not present yet as an active spider in `doxx`, but the old `E-katalog` parser should be used when this store is migrated in.

### Port to new boundary, but not by old reference

- `infrastructure/spiders/uzum.py`
  `E-katalog` does not provide the right reference here. Keep its store-specific logic, but port it to the new raw-output and Scraper DB contract.

## New architecture map

Target logical project layout:

```text
services/
  scraper/
    README.md
  publisher/
    README.md

shared/
  contracts/
    README.md
    scraper_product_event.schema.json
    scraper_product_event.example.json
  db/
    README.md
    schema.sql

infra/
  rabbitmq/
    README.md
    topology.json
```

Current runtime anchors already added in the repo:

- scraper-side persistence foundation:
  `infrastructure/pipelines/scraper_storage_pipeline.py`
- local DB adapter / outbox prototype:
  `infrastructure/persistence/sqlite_store.py`
- minimal snapshot model:
  `domain/scraped_product.py`
- publisher foundation:
  `services/publisher/publication_worker.py`
- message contract model:
  `domain/publication_event.py`

## Service responsibilities

### Scraper Service

Owns:

- spider execution
- listing -> PDP traversal
- store-specific selectors
- source id extraction
- raw specs extraction
- image extraction
- whitespace cleanup
- boolean stock normalization
- category hint extraction
- saving each item into Scraper DB
- creating outbox rows in the same transaction

Does not own:

- CRM delivery
- deep normalization
- canonical matching
- final downstream product model
- multi-store dedupe

### Publisher Service

Owns:

- claiming unpublished outbox rows
- publishing to RabbitMQ
- recording attempts
- retries and terminal failures
- replay from persisted outbox state

Does not own:

- scraping logic
- spiders
- store selectors
- CRM or downstream business rules

### RabbitMQ

RabbitMQ is the **final boundary of scraper-side responsibility**.

The scraper project is considered successful when:

1. the scraped payload is durably stored in Scraper DB
2. the outbox row is durably stored
3. the publisher successfully publishes the message to RabbitMQ

Everything after that belongs to downstream systems.

## Data flow

```text
Store Spider
  -> minimal structured raw item
  -> Scraper DB (`raw_products`, `raw_product_images`, `raw_product_specs`)
  -> `publication_outbox`
  -> Publisher Service
  -> RabbitMQ exchange
```

## Why scraper no longer sends directly to CRM

- CRM is not the scraper boundary.
- Direct CRM send couples scrape quality, downstream schema, and transport availability into one failure domain.
- It makes replay hard because the source-of-truth scrape payload is not durably preserved on the scraper side.
- It forces the scraper to know too much about downstream business rules.
- It invites hybrid architectures like “sometimes RabbitMQ, sometimes CRM, sometimes both”.

The scraper must stop at RabbitMQ. That is the clean system boundary.

## Why Scraper DB is mandatory

Scraper DB is required because the scraper side must have durable ownership of:

- what was scraped
- when it was scraped
- which run produced it
- which fields were missing
- what was attempted for publication
- what needs replay

Without a DB:

- replay is unreliable
- audit is weak
- XLSX export is awkward
- field coverage analysis is fragile
- scrape quality investigation depends on logs instead of durable records

## Why outbox/publication layer is mandatory

The outbox layer is mandatory because:

- scraper and publisher must be decoupled
- scraper success must not depend on broker availability at scrape time
- retries must be driven by persistent state, not in-memory queues
- publication history must be queryable for audit and replay

The outbox is the only safe place to encode publication state.

## Why deep normalization is removed from scraper

Deep normalization is removed because the scraper service should optimize for:

- store resilience
- source fidelity
- debuggability
- predictable persistence

Deep normalization causes the scraper to absorb downstream concerns:

- canonical matching
- spec typing as the main value layer
- business-facing product shape decisions
- cross-store merge rules

That makes scraping brittle and mixes responsibilities. The scraper should preserve raw truth with only minimal structuring.

## Why this is better for XLSX export, replay, audit, and resilience

### XLSX export

Raw products, raw specs, and images are stored in explicit rows, so export becomes a DB query problem, not a log-mining problem.

### Replay

Outbox rows and publication attempts make replay safe, bounded, and observable.

### Audit

Each scrape run, product snapshot, and publication attempt is durable and queryable.

### Resilience

Scraping can continue even if RabbitMQ is temporarily unavailable because publication is decoupled by outbox persistence.

## Scraper DB tables

The target relational schema is defined in `shared/db/schema.sql`.

### `scrape_runs`

Purpose:
Track one crawl run per store/spider execution and aggregate run-level diagnostics.

Key fields:

- `scrape_run_id`
- `store_name`
- `spider_name`
- `started_at`
- `finished_at`
- `status`

Constraints:

- primary key on `scrape_run_id`

Indexes:

- `(store_name, started_at desc)`

Retention expectation:

- Keep longer than raw rows; useful for operational trend analysis and audits.
- Reasonable default: 6-12 months, potentially longer in low-volume environments.

### `raw_products`

Purpose:
Store one minimally structured raw product snapshot per run.

Key fields:

- `raw_product_id`
- `scrape_run_id`
- `store_name`
- `source_url`
- `source_id`
- `title`
- `brand`
- `price_raw`
- `in_stock`
- `description`
- `category_hint`
- `payload_hash`
- `raw_payload_snapshot`
- `scraped_at`

Constraints:

- FK to `scrape_runs`
- unique `(scrape_run_id, store_name, source_url)`
- unique `(scrape_run_id, store_name, payload_hash)`

Indexes:

- `(store_name, source_id)`
- `(payload_hash)`
- `(scraped_at desc)`

Retention expectation:

- Keep long enough for replay, audit, XLSX export, and quality analysis.
- Reasonable default: 90-180 days minimum.

### `raw_product_images`

Purpose:
Store image URLs as first-class rows instead of burying them in a blob.

Key fields:

- `raw_product_image_id`
- `raw_product_id`
- `image_url`
- `sort_order`

Constraints:

- FK to `raw_products`
- unique `(raw_product_id, image_url)`

Indexes:

- `(raw_product_id, sort_order asc)`

Retention expectation:

- Same as `raw_products`, because images are part of the scrape snapshot.

### `raw_product_specs`

Purpose:
Store raw specs as first-class rows for export, coverage checks, diffing, and queryability.

Key fields:

- `raw_product_spec_id`
- `raw_product_id`
- `spec_name`
- `spec_value`
- `sort_order`

Constraints:

- FK to `raw_products`
- unique `(raw_product_id, spec_name, spec_value)`

Indexes:

- `(raw_product_id, sort_order asc)`
- `(spec_name)`

Retention expectation:

- Same as `raw_products`.

### `publication_outbox`

Purpose:
Persistent publication queue owned by the scraper contour.

Key fields:

- `event_id`
- `raw_product_id`
- `scrape_run_id`
- `event_type`
- `schema_version`
- `store_name`
- `source_id`
- `source_url`
- `payload_hash`
- `exchange_name`
- `routing_key`
- `status`
- `retry_count`
- `available_at`
- `lease_owner`
- `lease_expires_at`
- `published_at`
- `last_error_code`
- `last_error_message`
- `payload_json`

Constraints:

- primary key on `event_id`
- FK to `raw_products`
- FK to `scrape_runs`

Indexes:

- `(status, available_at asc)`
- `(store_name, status, created_at asc)`
- `(payload_hash)`

Retention expectation:

- Keep published rows long enough for replay windows and audit.
- Reasonable default: 30-90 days for published, longer for failed rows if storage allows.

### `publication_attempts`

Purpose:
Store every publish attempt for audit and troubleshooting.

Key fields:

- `publication_attempt_id`
- `event_id`
- `attempt_number`
- `attempted_at`
- `status`
- `publisher_service`
- `error_code`
- `error_message`
- `broker_message_id`
- `response_metadata`

Constraints:

- FK to `publication_outbox`
- unique `(event_id, attempt_number)`

Indexes:

- `(event_id, attempted_at desc)`

Retention expectation:

- Keep at least as long as outbox rows, preferably longer for failure analytics.

## RabbitMQ message contract

Target contract files:

- `shared/contracts/scraper_product_event.schema.json`
- `shared/contracts/scraper_product_event.example.json`

Minimum envelope fields:

- `event_id`
- `event_type`
- `schema_version`
- `scrape_run_id`
- `store_name`
- `source_id`
- `source_url`
- `scraped_at`
- `payload_hash`
- `structured_payload`
- `publication`

Minimum `structured_payload` payload fields:

- `store_name`
- `source_url`
- `source_id`
- `title`
- `brand`
- `price_raw`
- `in_stock`
- `raw_specs`
- `image_urls`
- `description`
- `category_hint`
- `external_ids`
- `scraped_at`
- `payload_hash`
- `raw_payload_snapshot`

## Idempotency strategy

- `payload_hash` is the business fingerprint of the minimally structured raw payload.
- `event_id` should be deterministic from the outbox row identity, not random per retry.
- `publication_outbox` must ensure one logical event row per persisted raw snapshot.
- Downstream consumers should be able to dedupe by `(event_id)` or `(store_name, source_id, payload_hash)`.

## Retry strategy

- Retries are driven only by `publication_outbox`, never by transient in-memory queues.
- Retryable failures move row state to `retryable`.
- Terminal failures move row state to `failed`.
- `available_at` controls backoff scheduling.
- `retry_count` caps retries and prevents infinite loops.

## Outbox semantics

- Scraper writes raw snapshot and outbox row in the same DB transaction.
- Publisher claims rows with a lease.
- Claimed rows move to `publishing`.
- Successful publish moves row to `published`.
- Failed publish moves row to `retryable` or `failed`.
- Attempt history is always appended to `publication_attempts`.

## Replay semantics

- Replay reads previously persisted rows from `publication_outbox` or reconstructs new outbox rows from `raw_products`.
- Replay must be bounded by:
  - store
  - scrape run
  - time window
  - status
  - max volume
- Replay never re-scrapes the store; it republishes persisted scraper-owned data.

## Error states

Expected outbox states:

- `pending`
  Row created but not yet claimed.
- `publishing`
  Row currently leased by a publisher.
- `published`
  Successfully sent to RabbitMQ.
- `retryable`
  Failed, but may be tried again.
- `failed`
  Terminal failure requiring operator review or manual replay decision.

Expected run states:

- `running`
- `completed`
- `partial_failure`
- `failed`

## New structure after stage 1

Physical target directories now present in the repo:

- `services/scraper/`
- `services/publisher/`
- `shared/contracts/`
- `shared/db/`
- `infra/rabbitmq/`

Foundation runtime anchors already present:

- `infrastructure/pipelines/scraper_storage_pipeline.py`
- `infrastructure/persistence/sqlite_store.py`
- `services/publisher/publication_worker.py`
- `domain/publication_event.py`

## Which old parts in `doxx` should be deleted or weakened

Delete from active runtime first:

- `NormalizePipeline`
- `SyncPipeline`
- `PublishPipeline`
- transport selection between CRM and Rabbit as an in-process scrape concern

Weaken into legacy-only code:

- `application/lifecycle/*`
- `application/extractors/*` as active scrape dependency
- `domain/crm_*`
- `infrastructure/transports/*`

Keep as migration support only:

- existing CRM-facing tests and docs, until the rest of the repo is fully cut over

## Why this is the correct base for MediaPark-first migration

- `MediaPark` is the strongest old reference in `E-katalog`.
- The migration priority is scraping resilience, not downstream shaping.
- MediaPark has enough complexity in listing traversal, PDP extraction, source id extraction, and raw specs extraction to validate the new architecture properly.
- If MediaPark works through `Scraper DB -> outbox -> Publisher -> RabbitMQ`, the same template can then be applied to Texnomart and the rest of the store set.
