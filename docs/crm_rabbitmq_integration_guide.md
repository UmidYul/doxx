# CRM RabbitMQ Integration Guide

## Overview

This file documents the actual RabbitMQ integration boundary implemented in `UmidYul/doxx`.

Active runtime flow:

`spider -> scraper DB -> publication_outbox -> publisher service -> RabbitMQ -> CRM consumer`

Scraper responsibility ends after:

- the product snapshot is durably stored in scraper SQLite;
- an outbox row is created;
- the standalone publisher service successfully publishes the event to RabbitMQ.

CRM responsibility starts after the message is available on RabbitMQ. CRM must:

- bind its own queue to the scraper exchange;
- read and validate the JSON event;
- persist the raw inbound event;
- enforce idempotency;
- normalize and store business data on the CRM side;
- `ack` only after durable CRM-side persistence succeeds.

### Source of truth

If any older documentation differs from runtime behavior, use these files as source of truth, in this order:

1. `services/publisher/rabbit_publisher.py`
2. `services/publisher/publication_worker.py`
3. `infrastructure/persistence/sqlite_store.py`
4. `domain/publication_event.py`
5. `application/ingestion/event_builder.py`
6. `shared/contracts/scraper_product_event.schema.json`
7. `infra/rabbitmq/topology.json`
8. publisher / integration tests under `tests/unit` and `tests/integration`

Important: this runtime contract is not the legacy CloudEvents contract from `application/message_builder.py` / `domain/message.py`. The standalone publisher actually sends `ScraperProductEvent` JSON from `domain/publication_event.py`.

## Actual topology

Confirmed runtime values:

- Exchange: `moscraper.events`
- Exchange type: `topic`
- Scraper-owned runtime queue: `scraper.products.v1`
- Routing key: `listing.scraped.v1`
- Event type inside JSON body: `scraper.product.scraped.v1`
- Message schema version: `1`
- Publication metadata version: `1`

Publisher behavior confirmed in `services/publisher/rabbit_publisher.py`:

- exchange is declared durable;
- queue is declared durable;
- queue is bound to the exchange with routing key `listing.scraped.v1`;
- publisher uses publisher confirms;
- message delivery mode is persistent.

### Recommended CRM queue strategy

Do not consume directly from the scraper-owned queue `scraper.products.v1` in production unless the CRM team intentionally accepts scraper-owned topology coupling.

Recommended strategy:

- CRM creates its own queue;
- CRM binds that queue to `moscraper.events` using `listing.scraped.v1`;
- CRM manages its own prefetch, retry, dead-lettering, and retention independently.

The scraper runtime does not define a CRM queue name. If you need a concrete convention, the existing repo docs use `crm.products.import.v1` as an example CRM-owned queue name, but that name is not runtime-owned by scraper.

### Bind strategy

Recommended bind:

- exchange: `moscraper.events`
- routing key: `listing.scraped.v1`
- queue: CRM-owned queue, for example `crm.products.import.v1`

## Connection settings

Actual scraper-side env names:

- `RABBITMQ_URL`
- `RABBITMQ_EXCHANGE`
- `RABBITMQ_EXCHANGE_TYPE`
- `RABBITMQ_QUEUE`
- `RABBITMQ_ROUTING_KEY`
- `RABBITMQ_PUBLISH_MANDATORY`

Actual defaults from `config/settings.py` and `.env.example`:

- `RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/`
- `RABBITMQ_EXCHANGE=moscraper.events`
- `RABBITMQ_EXCHANGE_TYPE=topic`
- `RABBITMQ_QUEUE=scraper.products.v1`
- `RABBITMQ_ROUTING_KEY=listing.scraped.v1`
- `RABBITMQ_PUBLISH_MANDATORY=true`

Connection details implied by the default URL:

- host: `rabbitmq`
- port: `5672`
- vhost: default `/`
- username: `guest`
- password: `guest`

Local docker-compose also exposes:

- AMQP: `localhost:5672`
- RabbitMQ management UI: `localhost:15672`

Example CRM env:

```env
CRM_RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
CRM_RABBITMQ_EXCHANGE=moscraper.events
CRM_RABBITMQ_EXCHANGE_TYPE=topic
CRM_RABBITMQ_ROUTING_KEY=listing.scraped.v1
CRM_RABBITMQ_QUEUE=crm.products.import.v1
CRM_RABBITMQ_PREFETCH=20
```

Notes:

- heartbeat is not explicitly configured by scraper code; use your RabbitMQ client defaults or set CRM-side heartbeat explicitly;
- reconnect is expected on the consumer side; scraper uses `aio_pika.connect_robust`, but CRM implementation is independent;
- TLS is not configured anywhere in scraper runtime; if production requires TLS, that is a deployment concern and the URL must change to a TLS-capable broker endpoint.

## Recommended CRM consumer flow

Recommended processing sequence:

1. Receive RabbitMQ message from CRM-owned queue.
2. Check AMQP metadata:
   - `content_type` should be `application/json`
   - `message_id` should match `event_id`
   - `type` should be `scraper.product.scraped.v1`
3. Parse UTF-8 JSON body.
4. Validate envelope:
   - required top-level fields present;
   - `event_type == "scraper.product.scraped.v1"`;
   - `schema_version == 1`;
   - `structured_payload` object present;
   - `publication` object present.
5. Validate business identity fields:
   - `structured_payload.identity_key`;
   - `store_name`;
   - `source_url`;
   - `payload_hash`;
   - `structured_payload.title`.
6. Save raw inbound event before destructive normalization:
   - full raw body;
   - AMQP metadata;
   - receive timestamp;
   - processing status `received`.
7. Perform idempotency check:
   - primary: `event_id`;
   - secondary: `payload_hash + store_name + source_id` when `source_id` exists;
   - stronger business key: `structured_payload.identity_key + payload_hash`.
8. If duplicate event:
   - mark duplicate in CRM-side inbound log;
   - `ack`.
9. Normalize / map into CRM product model.
10. Persist product upsert and inbound-event status in one transaction where possible.
11. Mark inbound event as processed.
12. Only then `ack`.

Do not `ack` before CRM has durably written:

- the raw inbound event record;
- the dedupe record;
- the product upsert or explicit duplicate status.

## Message contract

The actual published JSON body is `ScraperProductEvent`.

### Top-level fields

| Field | Type | Required | Nullable | Purpose | Example |
|---|---|---|---|---|---|
| `event_id` | `string` | yes | no | Stable event identifier for the outbox row | `715883cd-8257-5db8-aa68-4d18d3b28552` |
| `event_type` | `string` | yes | no | Event name; current runtime value is fixed | `scraper.product.scraped.v1` |
| `schema_version` | `integer` | yes | no | Message contract version | `1` |
| `store_name` | `string` | yes | no | Store source name | `mediapark` |
| `source_id` | `string` | no | yes | Store-local product identifier | `32771` |
| `source_url` | `string` | yes | no | Source product page URL | `https://mediapark.uz/products/view/...` |
| `scrape_run_id` | `string` | yes | no | Scrape run identifier | `run_mediapark_20260403_120000` |
| `scraped_at` | `string(date-time)` | yes | no | UTC timestamp of scraping | `2026-04-03T12:00:15Z` |
| `payload_hash` | `string` | yes | no | Scraper-computed business payload fingerprint | `sha256:7ab4...` |
| `structured_payload` | `object` | yes | no | Main product payload block | `{...}` |
| `publication` | `object` | yes | no | Publisher/outbox metadata | `{...}` |

### AMQP properties sent with the message

Confirmed in `services/publisher/rabbit_publisher.py`:

| AMQP field | Value |
|---|---|
| `delivery_mode` | `persistent` |
| `content_type` | `application/json` |
| `message_id` | `event.event_id` |
| `type` | `event.event_type` |
| `headers.schema_version` | `event.schema_version` |
| `headers.store_name` | `event.store_name` |
| `headers.scrape_run_id` | `event.scrape_run_id` |
| `headers.payload_hash` | `event.payload_hash` |

## Structured payload contract

The main business payload is under `structured_payload`.

| Field | Type | Required | Nullable | Purpose | Example |
|---|---|---|---|---|---|
| `structured_payload.store_name` | `string` | yes | no | Duplicates top-level store name | `mediapark` |
| `structured_payload.source_url` | `string` | yes | no | Duplicates top-level source URL | `https://mediapark.uz/products/view/...` |
| `structured_payload.source_id` | `string` | no | yes | Duplicates top-level source id | `32771` |
| `structured_payload.title` | `string` | yes | no | Product title | `Samsung Galaxy Z Flip 7 Black 12/256` |
| `structured_payload.brand` | `string` | no | yes | Best-effort brand | `Samsung` |
| `structured_payload.price_raw` | `string` | no | yes | Raw price string from scraper | `14999000` |
| `structured_payload.in_stock` | `boolean` | no | yes | Best-effort stock state | `true` |
| `structured_payload.raw_specs` | `object` | yes | no | Raw source specs map; dynamic shape | `{"Оперативная память":"12 ГБ"}` |
| `structured_payload.image_urls` | `array[string]` | yes | no | Product images; may be empty | `["https://.../main.jpg"]` |
| `structured_payload.description` | `string` | no | yes | Raw description | `Складной смартфон...` |
| `structured_payload.category_hint` | `string` | no | yes | Best-effort source category hint | `phone` |
| `structured_payload.external_ids` | `object<string,string>` | no | no | External IDs map; may be empty | `{"mediapark":"32771"}` |
| `structured_payload.scraped_at` | `string(date-time)` | yes | no | Duplicates scrape time | `2026-04-03T12:00:15Z` |
| `structured_payload.payload_hash` | `string` | yes | no | Duplicates top-level payload hash | `sha256:7ab4...` |
| `structured_payload.raw_payload_snapshot` | `object` | yes | no | Scraper-side raw payload snapshot with `_`-prefixed keys removed | `{"title":"Samsung Galaxy..."}` |
| `structured_payload.scrape_run_id` | `string` | yes | no | Duplicates run id | `run_mediapark_20260403_120000` |
| `structured_payload.identity_key` | `string` | yes | no | Scraper-computed stable source-product key | `mediapark:32771` |

### Publication metadata contract

`publication` is delivery metadata, not product data.

| Field | Type | Required | Nullable | Purpose | Example |
|---|---|---|---|---|---|
| `publication.publication_version` | `integer` | yes | no | Publication metadata version | `1` |
| `publication.exchange_name` | `string` | no | yes | Exchange used by publisher | `moscraper.events` |
| `publication.queue_name` | `string` | no | yes | Scraper-owned queue configured in publisher | `scraper.products.v1` |
| `publication.routing_key` | `string` | no | yes | Routing key used by publisher | `listing.scraped.v1` |
| `publication.outbox_status` | `string` | yes | no | Outbox status at publish time | `publishing` |
| `publication.attempt_number` | `integer` | no | no | Publish attempt number | `1` |
| `publication.publisher_service` | `string` | no | yes | Publisher service name | `publisher-service` |
| `publication.outbox_created_at` | `string(date-time)` | yes | no | Outbox row creation time | `2026-04-03T12:00:16Z` |
| `publication.published_at` | `string(date-time)` | no | yes | `null` in the published runtime message | `null` |

### Dynamic and nested fields

Dynamic shapes that CRM must not hard-code as fixed schemas:

- `structured_payload.raw_specs`
  Dynamic object. Keys depend on store and category. Values can be strings, nested objects, or arrays after scraper-side normalization.
- `structured_payload.image_urls`
  Ordered array of strings after dedupe.
- `structured_payload.external_ids`
  Dynamic object map of string keys to string values.
- `structured_payload.raw_payload_snapshot`
  Raw snapshot object. Shape is intentionally not fixed.

## Validation rules for CRM

### Fields CRM should treat as mandatory for successful processing

Envelope mandatory:

- `event_id`
- `event_type`
- `schema_version`
- `store_name`
- `source_url`
- `scrape_run_id`
- `scraped_at`
- `payload_hash`
- `structured_payload`
- `publication`

Structured payload mandatory:

- `structured_payload.store_name`
- `structured_payload.source_url`
- `structured_payload.title`
- `structured_payload.raw_specs`
- `structured_payload.image_urls`
- `structured_payload.scraped_at`
- `structured_payload.payload_hash`
- `structured_payload.raw_payload_snapshot`
- `structured_payload.scrape_run_id`
- `structured_payload.identity_key`

Publication mandatory:

- `publication.publication_version`
- `publication.outbox_status`
- `publication.outbox_created_at`

### Fields CRM should prefer but not require

- `source_id`
- `structured_payload.source_id`
- `structured_payload.brand`
- `structured_payload.price_raw`
- `structured_payload.in_stock`
- `structured_payload.description`
- `structured_payload.category_hint`
- `structured_payload.external_ids`
- `publication.exchange_name`
- `publication.queue_name`
- `publication.routing_key`
- `publication.publisher_service`
- `publication.attempt_number`

### Cross-field validation CRM should perform

- top-level `event_type` must equal `scraper.product.scraped.v1`;
- top-level `schema_version` must equal `1`;
- top-level `payload_hash` should equal `structured_payload.payload_hash`;
- top-level `store_name` should equal `structured_payload.store_name`;
- top-level `source_url` should equal `structured_payload.source_url`;
- top-level `scrape_run_id` should equal `structured_payload.scrape_run_id`;
- top-level `scraped_at` should equal `structured_payload.scraped_at`;
- if `source_id` is present, it should match `structured_payload.source_id`.

### Reject vs accept with degraded path

Reject / quarantine:

- invalid JSON;
- non-JSON `content_type`;
- unknown `event_type`;
- unsupported `schema_version`;
- missing `event_id`;
- missing `structured_payload.identity_key`;
- missing `structured_payload.title`;
- missing `store_name` or `source_url`;
- payload hash mismatch between top-level and `structured_payload`.

Accept with degraded path:

- `brand == null`;
- `price_raw == null`;
- `in_stock == null`;
- `description == null`;
- `category_hint == null`;
- empty `raw_specs`;
- empty `image_urls`;
- empty `external_ids`;
- `source_id == null` if `identity_key` and `source_url` are present.

## Ack / Nack / Retry semantics

Recommended CRM behavior:

### `ack`

Do `ack` when:

- raw inbound event is saved;
- idempotency record is saved or confirmed duplicate;
- business persistence completed successfully;
- duplicate was safely detected and recorded.

### `nack` with requeue / retry

Do retryable handling for transient failures:

- CRM database temporarily unavailable;
- transaction deadlock / lock timeout;
- temporary network dependency failure inside CRM;
- temporary storage outage for raw inbound event persistence.

Use bounded retries. Do not create infinite poison-message loops.

### Reject without requeue

Reject to DLQ / quarantine when the message is non-retryable:

- invalid JSON;
- unsupported `schema_version`;
- unknown `event_type`;
- missing required structural fields;
- impossible type/shape mismatch;
- permanent normalization error caused by invalid input shape.

### Poison message discipline

If the same event repeatedly fails for a non-transient reason:

- save the failure details in CRM;
- dead-letter or quarantine the message;
- do not keep requeueing forever.

Why `ack` must not happen early:

- RabbitMQ delivery is at-least-once;
- if CRM `ack`s before durable write and then crashes, the event is lost to CRM;
- scraper publisher already finished its responsibility at publish time and will not repair CRM-side premature acknowledgements.

## Idempotency rules

### Primary rule

Deduplicate by `event_id`.

Reason:

- `event_id` is deterministic per outbox row;
- it is generated in `SQLiteScraperStore.persist_snapshot()` as:
  `uuid5(NAMESPACE_URL, "outbox:{scrape_run_id}:{identity_key}")`
- publisher retries do not create a new `event_id`.

### Secondary safety rules

Use at least one business-level dedupe check in addition to `event_id`:

- preferred: `structured_payload.identity_key + payload_hash`
- requested secondary fallback: `payload_hash + store_name + source_id`

Reason:

- duplicate broker deliveries of the same event should collapse by `event_id`;
- re-scraped identical business state for the same product should collapse by business key + hash;
- `source_id` can be null, so `identity_key + payload_hash` is the safer CRM-side invariant.

### Recommended CRM table

Example table: `consumed_events`

Suggested columns:

- `event_id` unique
- `event_type`
- `schema_version`
- `store_name`
- `source_id`
- `source_url`
- `identity_key`
- `payload_hash`
- `scrape_run_id`
- `received_at`
- `processed_at`
- `status` (`received`, `processed`, `duplicate`, `retryable_failed`, `terminal_failed`)
- `error_message`
- `raw_event_json`
- `parsed_payload_json`

Recommended statuses:

- `received`
- `processed`
- `duplicate`
- `retryable_failed`
- `terminal_failed`

## Raw inbound storage recommendation

CRM should persist raw inbound data because it gives:

- auditability;
- replay support;
- forensic traceability;
- exact visibility into what scraper actually sent;
- protection against normalization bugs on the CRM side.

Persist at least:

- original raw JSON body;
- parsed payload JSON;
- AMQP metadata used by CRM;
- receive timestamp;
- processing status;
- error details if processing fails;
- `event_id`;
- `payload_hash`;
- `identity_key`;
- `scrape_run_id`;
- `store_name`;
- `source_url`.

## Error handling

| Situation | CRM action |
|---|---|
| Invalid JSON | Save raw bytes if possible, reject without requeue, move to DLQ/quarantine |
| `content_type` not `application/json` | Reject without requeue |
| Unsupported `schema_version` | Reject without requeue |
| Unknown `event_type` | Reject without requeue |
| Missing required fields | Reject without requeue |
| Top-level / structured payload mismatch | Reject without requeue |
| Duplicate `event_id` | Record duplicate, `ack` |
| Same `identity_key + payload_hash` already applied | Record duplicate/no-op, `ack` |
| DB transient failure | `nack` or retry via retry queue |
| Temporary infrastructure failure while saving raw event | `nack` / retry |
| Normalization error caused by permanently bad payload | Record failure, reject without requeue |
| Partial payload with nullable optional fields only | Process in degraded mode, `ack` after save |

## Example message

This example is aligned to the actual runtime shape published by the standalone publisher service.

```json
{
  "event_id": "715883cd-8257-5db8-aa68-4d18d3b28552",
  "event_type": "scraper.product.scraped.v1",
  "schema_version": 1,
  "store_name": "mediapark",
  "source_id": "32771",
  "source_url": "https://mediapark.uz/products/view/smartfon-samsung-galaxy-z-flip-7-black-12-256-32771",
  "scrape_run_id": "run_mediapark_20260403_120000",
  "scraped_at": "2026-04-03T12:00:15Z",
  "payload_hash": "sha256:7ab4ec7f4a977f5c31df5a0b82c0ce11f298f389d17410c3447b9af6ca0bc1a0",
  "structured_payload": {
    "store_name": "mediapark",
    "source_url": "https://mediapark.uz/products/view/smartfon-samsung-galaxy-z-flip-7-black-12-256-32771",
    "source_id": "32771",
    "title": "Samsung Galaxy Z Flip 7 Black 12/256",
    "brand": "Samsung",
    "price_raw": "14999000",
    "in_stock": true,
    "raw_specs": {
      "Оперативная память": "12 ГБ",
      "Встроенная память": "256 ГБ",
      "Цвет": "Black"
    },
    "image_urls": [
      "https://mediapark.uz/img/products/32771/main.jpg",
      "https://mediapark.uz/img/products/32771/gallery-2.jpg"
    ],
    "description": "Складной смартфон Samsung Galaxy Z Flip 7.",
    "category_hint": "phone",
    "external_ids": {
      "mediapark": "32771"
    },
    "scraped_at": "2026-04-03T12:00:15Z",
    "payload_hash": "sha256:7ab4ec7f4a977f5c31df5a0b82c0ce11f298f389d17410c3447b9af6ca0bc1a0",
    "raw_payload_snapshot": {
      "source": "mediapark",
      "url": "https://mediapark.uz/products/view/smartfon-samsung-galaxy-z-flip-7-black-12-256-32771",
      "source_id": "32771",
      "title": "Samsung Galaxy Z Flip 7 Black 12/256",
      "brand": "Samsung",
      "price_str": "14999000",
      "in_stock": true,
      "raw_specs": {
        "Оперативная память": "12 ГБ"
      },
      "image_urls": [
        "https://mediapark.uz/img/products/32771/main.jpg"
      ]
    },
    "scrape_run_id": "run_mediapark_20260403_120000",
    "identity_key": "mediapark:32771"
  },
  "publication": {
    "publication_version": 1,
    "exchange_name": "moscraper.events",
    "queue_name": "scraper.products.v1",
    "routing_key": "listing.scraped.v1",
    "outbox_status": "publishing",
    "attempt_number": 1,
    "publisher_service": "publisher-service",
    "outbox_created_at": "2026-04-03T12:00:16Z",
    "published_at": null
  }
}
```

## Minimal CRM implementation checklist

- Create a CRM-owned queue.
- Bind it to `moscraper.events` with routing key `listing.scraped.v1`.
- Parse JSON body as `ScraperProductEvent`.
- Validate `event_type == scraper.product.scraped.v1`.
- Validate `schema_version == 1`.
- Validate required envelope and `structured_payload` fields.
- Save raw inbound event.
- Run idempotency checks.
- Normalize and persist product state.
- Mark inbound event status.
- `ack` only after durable success.

## Integration notes / pitfalls

- Do not read directly from `scraper.products.v1` unless you intentionally accept coupling to scraper-owned topology.
- Do not implement the legacy CloudEvents shape for this consumer; it is not the active RabbitMQ runtime contract.
- Do not `ack` before CRM durable writes finish.
- Do not rely only on `source_id`; it can be null.
- Do not recompute `identity_key`; consume the provided value.
- Do not recompute `payload_hash` to decide whether the event is duplicate; use the producer value.
- Do not assume `raw_specs` is normalized or fixed-schema.
- Do not hard-fail when `brand`, `price_raw`, `description`, `category_hint`, or `source_id` are null.
- Do not drop the raw inbound payload; you will need it for audit and incident debugging.
- Do not treat `publication.outbox_status` as product business state; it is delivery metadata only.

## Field inventory

| field_path | type | required | description |
|---|---|---|---|
| `event_id` | `string` | yes | Stable event identifier for the outbox row |
| `event_type` | `string` | yes | Runtime event name, currently `scraper.product.scraped.v1` |
| `schema_version` | `integer` | yes | Message schema version |
| `store_name` | `string` | yes | Store source name |
| `source_id` | `string|null` | no | Store-local product id |
| `source_url` | `string` | yes | Product source URL |
| `scrape_run_id` | `string` | yes | Scrape run id |
| `scraped_at` | `string(date-time)` | yes | Scrape timestamp UTC |
| `payload_hash` | `string` | yes | Producer-computed business hash |
| `structured_payload` | `object` | yes | Main business payload |
| `structured_payload.store_name` | `string` | yes | Store source name duplicate |
| `structured_payload.source_url` | `string` | yes | Source URL duplicate |
| `structured_payload.source_id` | `string|null` | no | Source id duplicate |
| `structured_payload.title` | `string` | yes | Product title |
| `structured_payload.brand` | `string|null` | no | Brand |
| `structured_payload.price_raw` | `string|null` | no | Raw price |
| `structured_payload.in_stock` | `boolean|null` | no | Stock state |
| `structured_payload.raw_specs` | `object` | yes | Dynamic raw specs map |
| `structured_payload.image_urls` | `array[string]` | yes | Image URL list |
| `structured_payload.description` | `string|null` | no | Product description |
| `structured_payload.category_hint` | `string|null` | no | Category hint |
| `structured_payload.external_ids` | `object<string,string>` | no | External ids map |
| `structured_payload.scraped_at` | `string(date-time)` | yes | Scrape timestamp duplicate |
| `structured_payload.payload_hash` | `string` | yes | Payload hash duplicate |
| `structured_payload.raw_payload_snapshot` | `object` | yes | Raw scraper payload snapshot |
| `structured_payload.scrape_run_id` | `string` | yes | Scrape run duplicate |
| `structured_payload.identity_key` | `string` | yes | Stable source-product key |
| `publication` | `object` | yes | Publication metadata |
| `publication.publication_version` | `integer` | yes | Publication metadata version |
| `publication.exchange_name` | `string|null` | no | Exchange name used by publisher |
| `publication.queue_name` | `string|null` | no | Scraper-owned queue name |
| `publication.routing_key` | `string|null` | no | Routing key used by publisher |
| `publication.outbox_status` | `string` | yes | Outbox status at publish time |
| `publication.attempt_number` | `integer` | no | Publish attempt number |
| `publication.publisher_service` | `string|null` | no | Publisher service name |
| `publication.outbox_created_at` | `string(date-time)` | yes | Outbox creation timestamp |
| `publication.published_at` | `string(date-time)|null` | no | Published timestamp; runtime message sends `null` |

## Topology summary

| key | value |
|---|---|
| `exchange` | `moscraper.events` |
| `exchange_type` | `topic` |
| `routing_key` | `listing.scraped.v1` |
| `scraper_runtime_queue` | `scraper.products.v1` |
| `recommended_crm_queue` | CRM-owned queue; scraper runtime does not define one. Example from repo docs: `crm.products.import.v1` |
| `consumer_ack_mode` | manual ack after durable CRM persistence |
