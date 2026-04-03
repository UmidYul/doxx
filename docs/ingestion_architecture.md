# Ingestion Architecture

## Runtime flow

`Store Spider -> Raw/Structured Item -> Scraper DB -> Outbox -> Publisher Service -> RabbitMQ`

## File layout

- `infrastructure/spiders/`: store spiders; `mediapark.py` now follows the older E-katalog listing -> PDP extraction approach more closely.
- `domain/scraped_product.py`: minimally structured persisted snapshot model.
- `domain/publication_event.py`: RabbitMQ event contract owned by the scraper side.
- `application/ingestion/fingerprints.py`: stable identity and payload hash builders.
- `application/ingestion/event_builder.py`: converts a persisted snapshot into an outbox event payload.
- `infrastructure/persistence/sqlite_store.py`: scraper DB adapter with scrape runs, raw product persistence, outbox, and attempt history.
- `infrastructure/pipelines/scraper_storage_pipeline.py`: active Scrapy pipeline that persists every scraped item and creates an outbox row in the same transaction.
- `services/publisher/publication_worker.py`: standalone publisher worker that claims and delivers outbox rows.
- `services/publisher/main.py`: service entrypoint for one-shot or continuous publishing.
- `services/publisher/rabbit_publisher.py`: RabbitMQ publishing adapter and topology owner.
- `services/publisher/outbox_reader.py`: DB-backed outbox reader/marker for the publisher service.

## DB schema

### `scrape_runs`

- `scrape_run_id`
- `store_name`
- `spider_name`
- `started_at`
- `finished_at`
- `status`
- `category_urls_json`
- `stats_json`

### `raw_products`

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
- `scraped_at`
- `payload_hash`
- `raw_payload_json`
- `structured_payload_json`
- `publication_state`
- `created_at`
- `updated_at`

This table is append-per-run/useful-for-audit in practice because `identity_key` is stable per source identity, while snapshots remain separated across runs.

### `raw_product_images`

- `id`
- `raw_product_id`
- `image_url`
- `position`

### `raw_product_specs`

- `id`
- `raw_product_id`
- `spec_name`
- `spec_value`
- `source_section`
- `position`

## Outbox schema

### `publication_outbox`

- `event_id`
- `raw_product_id`
- `scrape_run_id`
- `store_name`
- `source_url`
- `source_id`
- `event_type`
- `exchange_name`
- `routing_key`
- `payload_hash`
- `status`
- `retry_count`
- `available_at`
- `lease_owner`
- `lease_expires_at`
- `published_at`
- `last_error`
- `payload_json`
- `created_at`
- `updated_at`

### `publication_attempts`

- `id`
- `outbox_id`
- `attempted_at`
- `success`
- `publisher_name`
- `attempt_number`
- `error_message`
- `created_at`

## RabbitMQ contract

Every message contains:

- `event_id`
- `event_type`
- `schema_version`
- `store_name`
- `source_id`
- `source_url`
- `scrape_run_id`
- `scraped_at`
- `payload_hash`
- `structured_payload`
- `publication`

`structured_payload` includes the structured raw scraper payload:

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
- `scrape_run_id`
- `identity_key`

`publication` includes the delivery metadata:

- `publication_version`
- `exchange_name`
- `queue_name`
- `routing_key`
- `outbox_status`
- `attempt_number`
- `publisher_service`
- `outbox_created_at`
- `published_at`

## Scraper flow

1. Spider yields a minimally structured product dict.
2. `ValidatePipeline` ensures required fields are present.
3. `ScraperStoragePipeline` builds `ScrapedProductSnapshot`.
4. `raw_products`, child image/spec rows, and the outbox payload are committed in one transaction.
5. Spider continues; scraper responsibility ends at durable DB write.

## Publisher flow

1. Publisher claims a batch of rows in `publication_outbox` using a lease.
2. Each row is published to RabbitMQ with persistent delivery mode.
3. Success marks outbox row `published` and writes `publication_attempts`.
4. Failure marks row `retryable` or `failed` with exponential backoff and attempt history.

## Migration plan by stores

1. Foundation: scraper DB, outbox, publisher, new event contract.
2. MediaPark: move first, because it is the reference scraper and most stability-sensitive store.
3. Store template: migrate remaining spiders to emit the same minimal raw snapshot contract.
4. Store-by-store migration from E-katalog selectors and listing/PDP traversal.
5. Acceptance tests: fixture parsing, DB persistence, outbox publish, broker integration.
6. Rollout: enable one store at a time, verify RabbitMQ events, inspect DB coverage and retries.

## Acceptance checks

- `python -m pytest tests/unit/test_sqlite_scraper_store.py -q`
- `python -m pytest tests/unit/test_outbox_publisher_service.py -q`
- `python -m pytest tests/unit/test_scrapy_settings_item_flow.py -q`
- `python -m pytest tests/acceptance/test_store_acceptance.py -q`
- `python -m pytest tests/integration/test_rabbit_publish.py -m integration -q`

## What to delete or replace in doxx

- Replace active `NormalizePipeline -> SyncPipeline` runtime with `ScraperStoragePipeline`.
- Stop using in-process CRM-oriented publish flow as the default delivery path.
- Remove fake-CRM operational scripts from the primary runbook.
- Gradually retire CRM/lifecycle/canonicalization code from the scraper runtime once the remaining stores are migrated onto the scraper DB/outbox boundary.
