# Scraper DB Schema

## Scope

This document describes the stage-2 scraper-side persistence layer for `doxx`.

Runtime flow:

`Store Spider -> minimal structured item -> Scraper DB -> publication_outbox`

This stage deliberately excludes:

- publisher service implementation details
- RabbitMQ delivery
- CRM-side logic
- deep normalization
- canonical matching

## Why this schema exists

The scraper must durably preserve each scraped product before any downstream publication happens.

This gives us:

- replay safety
- auditability per run and per product
- first-class XLSX export from SQL, not from logs
- visibility into images/specs completeness
- a stable outbox boundary for the later publisher service

## Data flow per item

1. Spider yields a minimally structured item.
2. `ScraperStoragePipeline` sends it to `ScraperPersistenceService`.
3. The service builds a `ScrapedProductSnapshot`.
4. The store writes or updates:
   - `raw_products`
   - `raw_product_images`
   - `raw_product_specs`
5. In the same DB transaction the store creates or refreshes one `publication_outbox` row.
6. `raw_products.publication_state` is set to `pending`.

## Tables

### `scrape_runs`

Purpose:
Track one scraper execution per spider/store and hold run-level counters.

Key fields:

- `id`
- `run_id`
- `store_name`
- `spider_name`
- `started_at`
- `finished_at`
- `status`
- `items_scraped`
- `items_persisted`
- `items_failed`

Constraints:

- PK on `id`
- unique on `run_id`

Indexes:

- `(store_name, started_at desc)`
- `(status, started_at desc)`

Retention:

- Keep long-term; it is small and useful for operational history.

### `raw_products`

Purpose:
Store one minimally structured raw product snapshot per `scrape_run_id + identity_key`.

Key fields:

- `id`
- `scrape_run_id`
- `store_name`
- `source_id`
- `source_url`
- `identity_key`
- `title`
- `brand`
- `price_raw`
- `in_stock`
- `description`
- `category_hint`
- `external_ids_json`
- `payload_hash`
- `raw_payload_json`
- `structured_payload_json`
- `scraped_at`
- `publication_state`

Constraints:

- FK `scrape_run_id -> scrape_runs.run_id`
- unique `(scrape_run_id, identity_key)`

Indexes:

- `(store_name, scraped_at desc)`
- `(scrape_run_id, scraped_at desc)`
- `(store_name, source_id)`
- `(store_name, source_url)`
- `(publication_state, scraped_at desc)`
- `(payload_hash)`

Retention:

- Keep long enough for replay, export, coverage analysis, and scrape-quality audits.

### `raw_product_images`

Purpose:
Store image URLs as first-class rows for export and completeness checks.

Key fields:

- `id`
- `raw_product_id`
- `image_url`
- `position`

Constraints:

- FK `raw_product_id -> raw_products.id`
- unique `(raw_product_id, image_url)`
- unique `(raw_product_id, position)`

Indexes:

- `(raw_product_id, position asc)`

Retention:

- Same as `raw_products`.

### `raw_product_specs`

Purpose:
Store flattened raw specs for SQL export and quality analysis while keeping the full raw spec blob in JSON.

Key fields:

- `id`
- `raw_product_id`
- `spec_name`
- `spec_value`
- `source_section`
- `position`

Constraints:

- FK `raw_product_id -> raw_products.id`
- unique `(raw_product_id, position)`
- unique index on `(raw_product_id, spec_name, spec_value, ifnull(source_section, ''))`

Indexes:

- `(raw_product_id, position asc)`
- `(spec_name)`

Retention:

- Same as `raw_products`.

### `publication_outbox`

Purpose:
Persistent publication queue owned by the scraper contour.

Key fields:

- `id`
- `raw_product_id`
- `event_id`
- `event_type`
- `schema_version`
- `scrape_run_id`
- `store_name`
- `source_id`
- `source_url`
- `payload_hash`
- `payload_json`
- `status`
- `available_at`
- `published_at`
- `retry_count`
- `last_error`

Constraints:

- PK on `id`
- unique on `event_id`
- unique on `raw_product_id`
- FK `raw_product_id -> raw_products.id`
- FK `scrape_run_id -> scrape_runs.run_id`

Indexes:

- `(status, available_at asc)`
- `(store_name, status, created_at asc)`
- `(scrape_run_id, created_at asc)`
- `(payload_hash)`

Retention:

- Keep published rows for replay windows and failed rows for investigation.

### `publication_attempts`

Purpose:
Audit every future publish attempt without coupling it to in-memory worker state.

Key fields:

- `id`
- `outbox_id`
- `attempt_number`
- `attempted_at`
- `success`
- `error_message`
- `publisher_name`

Constraints:

- FK `outbox_id -> publication_outbox.id`
- unique `(outbox_id, attempt_number)`

Indexes:

- `(outbox_id, attempted_at desc)`

Retention:

- Keep at least as long as `publication_outbox`, preferably longer.

## Update semantics

- A repeated scrape of the same product inside the same run updates the existing `raw_products` row via `identity_key`.
- Child rows in `raw_product_images` and `raw_product_specs` are replaced transactionally to reflect the latest scrape result for that run.
- The matching outbox row is updated in place and reset to `pending`.

## Why this is XLSX-friendly

- Product core fields live in `raw_products`.
- Images are already one row per image.
- Specs are already one row per name/value pair.
- Exporters can join `scrape_runs`, `raw_products`, `raw_product_images`, and `raw_product_specs` directly.
- `raw_payload_json` and `structured_payload_json` remain available for debug columns when needed.
