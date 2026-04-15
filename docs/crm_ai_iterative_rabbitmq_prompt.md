# Iterative Prompt For CRM AI: RabbitMQ Consumer Integration

## How To Use This Prompt

Paste this whole file into the CRM-side AI chat.

Important operating mode:

- Do not implement everything at once.
- Work strictly iteration by iteration.
- After each iteration, stop, summarize changes, list touched files, and wait for confirmation.
- If I say `continue`, move to the next unfinished iteration only.
- If the current CRM codebase already has similar infrastructure, reuse and adapt it instead of rebuilding from scratch.

## Mission

Integrate the CRM application with an external RabbitMQ broker hosted on another laptop.

The active upstream contour is:

`scraper -> scraper DB -> outbox -> publisher -> RabbitMQ -> CRM consumer`

Your job is to implement the CRM-side consumer safely and incrementally.

## Current Infrastructure Facts

These values are already real and should be treated as source-of-truth.

### Network

- RabbitMQ host laptop IP: `192.168.1.105`
- CRM laptop IP: `192.168.1.102`
- AMQP port: `5672`
- RabbitMQ management UI is local-only on the scraper laptop and is not needed by CRM

### RabbitMQ Access

- vhost: `moscraper`
- CRM username: `moscraper_crm`
- CRM password: `moscraper_crm_2026_secure`
- CRM AMQP URL:

```env
amqp://moscraper_crm:moscraper_crm_2026_secure@192.168.1.105:5672/moscraper
```

### RabbitMQ Topology

- producer exchange: `moscraper.events`
- producer exchange type: `topic`
- producer routing key: `listing.scraped.v1`

- CRM main queue: `crm.products.import.v1`
- CRM retry exchange: `crm.products.retry`
- CRM requeue exchange: `crm.products.requeue`
- CRM dead-letter exchange: `crm.products.dlx`
- CRM retry queues:
  - `crm.products.import.v1.retry.30s`
  - `crm.products.import.v1.retry.5m`
  - `crm.products.import.v1.retry.30m`
- CRM quarantine queue:
  - `crm.products.import.v1.dlq`

### RabbitMQ Permissions For CRM User

The CRM Rabbit user has these permissions in vhost `moscraper`:

- configure: `^$`
- write: `^crm\.products\.retry$`
- read: `^(crm\.products\.import\.v1|crm\.products\.import\.v1\.dlq)$`

This means:

- CRM must not try to declare or create exchanges or queues.
- CRM may consume from `crm.products.import.v1`.
- CRM may inspect or consume from `crm.products.import.v1.dlq` if needed.
- CRM may publish only to `crm.products.retry`.

## Non-Negotiable Rules

1. Consume only from `crm.products.import.v1`.
2. Do not consume `scraper.products.v1`.
3. Do not try to declare topology because the CRM user has no configure permission.
4. Use manual ack.
5. Ack only after durable CRM-side persistence succeeds.
6. Persist raw inbound event before destructive business mapping.
7. Primary dedupe key is `event_id`.
8. Secondary business dedupe key is `structured_payload.identity_key + payload_hash`.
9. Do not recompute `identity_key`.
10. Do not recompute `payload_hash` to decide duplicates.
11. Treat `publication` as delivery metadata only, not business state.
12. `source_id` may be null.
13. `structured_payload.raw_specs` is dynamic and may contain nested objects or arrays.
14. Do not create an infinite retry loop.

## Exact CRM Env To Add

Create or extend CRM env config with at least:

```env
CRM_RABBITMQ_ENABLED=true
CRM_RABBITMQ_URL=amqp://moscraper_crm:moscraper_crm_2026_secure@192.168.1.105:5672/moscraper
CRM_RABBITMQ_QUEUE=crm.products.import.v1
CRM_RABBITMQ_PREFETCH=20
CRM_RABBITMQ_HEARTBEAT_SECONDS=30
CRM_RABBITMQ_CONNECTION_NAME=crm-consumer

CRM_RABBITMQ_EXCHANGE=moscraper.events
CRM_RABBITMQ_EXCHANGE_TYPE=topic
CRM_RABBITMQ_ROUTING_KEY=listing.scraped.v1

CRM_RABBITMQ_RETRY_EXCHANGE=crm.products.retry
CRM_RABBITMQ_RETRY_KEY_30S=30s
CRM_RABBITMQ_RETRY_KEY_5M=5m
CRM_RABBITMQ_RETRY_KEY_30M=30m
CRM_RABBITMQ_DLQ=crm.products.import.v1.dlq

CRM_RABBITMQ_MAX_RETRY_STAGES=3
CRM_RABBITMQ_RETRY_HEADER_ATTEMPT=x-crm-retry-attempt
CRM_RABBITMQ_RETRY_HEADER_STAGE=x-crm-retry-stage
CRM_RABBITMQ_RETRY_HEADER_ORIGINAL_EVENT_ID=x-original-event-id
```

If the CRM project already has config naming conventions, adapt these names, but keep the semantics identical.

## Message Contract

The incoming message body is JSON with this top-level contract:

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

Expected fixed values:

- `event_type == "scraper.product.scraped.v1"`
- `schema_version == 1`

### Required `structured_payload` fields

- `store_name`
- `source_url`
- `title`
- `raw_specs`
- `image_urls`
- `scraped_at`
- `payload_hash`
- `raw_payload_snapshot`
- `scrape_run_id`
- `identity_key`

### Important optional fields

- `source_id`
- `brand`
- `price_raw`
- `in_stock`
- `description`
- `category_hint`
- `external_ids`

### Important `publication` fields

- `publication_version`
- `exchange_name`
- `queue_name`
- `routing_key`
- `outbox_status`
- `attempt_number`
- `publisher_service`
- `outbox_created_at`
- `published_at`

Important nuance:

- `publication.queue_name` will be `scraper.products.v1`
- this is correct
- it does not mean CRM should read from that queue

## Example Incoming Payload Shape

This is the shape, simplified:

```json
{
  "event_id": "evt_mediapark_20260403_000001",
  "event_type": "scraper.product.scraped.v1",
  "schema_version": 1,
  "scrape_run_id": "run_mediapark_20260403_120000",
  "store_name": "mediapark",
  "source_id": "32771",
  "source_url": "https://mediapark.uz/products/view/...",
  "scraped_at": "2026-04-03T12:00:15Z",
  "payload_hash": "sha256:...",
  "structured_payload": {
    "store_name": "mediapark",
    "source_url": "https://mediapark.uz/products/view/...",
    "source_id": "32771",
    "title": "Samsung Galaxy Z Flip 7 Black 12/256",
    "brand": "Samsung",
    "price_raw": "14999000",
    "in_stock": true,
    "raw_specs": {
      "Color": "Black"
    },
    "image_urls": [
      "https://mediapark.uz/img/products/32771/main.jpg"
    ],
    "description": "Product description",
    "category_hint": "phone",
    "external_ids": {
      "mediapark": "32771"
    },
    "scraped_at": "2026-04-03T12:00:15Z",
    "payload_hash": "sha256:...",
    "raw_payload_snapshot": {
      "title": "Samsung Galaxy Z Flip 7 Black 12/256"
    },
    "scrape_run_id": "run_mediapark_20260403_120000",
    "identity_key": "mediapark:32771"
  },
  "publication": {
    "publication_version": 1,
    "exchange_name": "moscraper.events",
    "queue_name": "scraper.products.v1",
    "routing_key": "listing.scraped.v1",
    "outbox_status": "published",
    "attempt_number": 1,
    "publisher_service": "publisher-service",
    "outbox_created_at": "2026-04-03T12:00:16Z",
    "published_at": "2026-04-03T12:00:17Z"
  }
}
```

## Required Processing Semantics

### Validation

Reject as invalid if any of these fail:

- body is not valid JSON
- `event_type` is not `scraper.product.scraped.v1`
- `schema_version` is not `1`
- `event_id` is missing
- `structured_payload.identity_key` is missing
- `structured_payload.title` is missing
- top-level `payload_hash` does not match `structured_payload.payload_hash`
- top-level `store_name` does not match `structured_payload.store_name`
- top-level `source_url` does not match `structured_payload.source_url`

### Duplicate Handling

Treat as duplicate and ack if:

- `event_id` already processed
- or business-level dedupe says `identity_key + payload_hash` already applied

### Retry Handling

For transient failures:

- publish a copy to `crm.products.retry`
- use routing key:
  - first retry: `30s`
  - second retry: `5m`
  - third retry: `30m`
- include or update headers:
  - `x-crm-retry-attempt`
  - `x-crm-retry-stage`
  - `x-original-event-id`
- ack the original message only after the retry publish succeeds

For permanent failures:

- reject without requeue from the main queue
- let Rabbit dead-letter it into `crm.products.import.v1.dlq`

After max retry stages are exhausted:

- treat the next failure as terminal
- reject without requeue

## Suggested Persistence Model

If the CRM codebase does not already have equivalent tables, create the minimal safe storage for:

### `crm_inbound_events`

Suggested columns:

- `id`
- `event_id` unique
- `event_type`
- `schema_version`
- `store_name`
- `source_id`
- `source_url`
- `scrape_run_id`
- `identity_key`
- `payload_hash`
- `retry_attempt`
- `retry_stage`
- `status`
- `received_at`
- `processed_at`
- `error_message`
- `raw_event_json`
- `headers_json`

### `crm_event_dedupe`

Suggested keys:

- unique `event_id`
- unique `(identity_key, payload_hash)` if that matches CRM domain rules

If the CRM already has an inbound-events or integration-events table, reuse it instead of creating new parallel structures.

## Iteration Plan

You must execute only one iteration at a time.

After finishing one iteration:

- stop
- summarize what changed
- list files touched
- list commands/tests run
- list blockers or assumptions
- wait for confirmation

### Iteration 0: Repository Audit Only

Goal:

- inspect the CRM codebase
- find existing message consumer infrastructure
- find config system
- find persistence layer
- find retry/error handling conventions

Do:

- locate current queue/worker/background job modules
- locate env/config modules
- locate models/tables suitable for inbound event persistence
- locate any current dedupe or webhook ingestion logic

Do not:

- write production code yet

Deliver:

- short integration map
- recommended files to change
- exact implementation plan adapted to the CRM repo

### Iteration 1: Config And Feature Flag Layer

Goal:

- add Rabbit consumer config only

Do:

- add env parsing
- add startup validation
- add feature flag / enable switch
- add typed config object

Do not:

- connect to Rabbit yet

Deliver:

- config code
- env example updates
- validation summary

### Iteration 2: Rabbit Connection Skeleton

Goal:

- add a safe consumer skeleton without business persistence

Do:

- create Rabbit connection factory
- create consumer bootstrap
- connect using CRM credentials
- consume only `crm.products.import.v1`
- use manual ack mode
- set prefetch

Do not:

- map product business data yet
- add retries yet

Deliver:

- connection module
- consumer runner
- logging of message receipt

### Iteration 3: Raw Inbound Event Persistence

Goal:

- durably store raw inbound messages before business mapping

Do:

- create or reuse inbound event persistence model
- save raw body
- save parsed JSON
- save headers
- save receive timestamp
- save initial status

Do not:

- ack on receive
- write product business entities yet

Deliver:

- persistence model
- repository/service methods
- status transitions for receive/store

### Iteration 4: Validation And Dedupe

Goal:

- validate payload and prevent duplicate reprocessing

Do:

- implement message shape validation
- implement top-level vs structured payload consistency checks
- implement `event_id` dedupe
- implement `identity_key + payload_hash` dedupe

Rules:

- duplicate -> record duplicate status -> ack
- invalid payload -> record terminal invalid status -> reject without requeue

Deliver:

- validator module
- dedupe path
- tests for valid/invalid/duplicate cases

### Iteration 5: CRM Business Mapping And Persistence

Goal:

- map validated inbound event into CRM product-side persistence

Do:

- connect the inbound event to the CRM domain model
- persist or update product data using existing CRM conventions
- keep raw event log and business write in a safe transaction if possible

Important:

- `raw_specs` is dynamic
- do not assume fixed schema for specs
- `source_id` may be null
- use `identity_key` as upstream stable identity

Deliver:

- business mapping code
- persistence integration
- success path with final ack only after durable write

### Iteration 6: Retry And Terminal Failure Discipline

Goal:

- implement transient retry path using the existing retry exchange

Do:

- classify transient vs permanent failures
- publish transient failures to `crm.products.retry`
- stage retries through `30s`, `5m`, `30m`
- reject terminal failures without requeue

Rules:

- ack original only if retry publish succeeds
- do not use infinite requeue
- after max retry stages, terminal failure must go to DLQ

Deliver:

- retry classifier
- retry publisher
- terminal failure path
- tests for retry stage progression

### Iteration 7: Observability, Smoke Test, And Ops Notes

Goal:

- make the integration operable

Do:

- add structured logs
- add a small smoke test or integration command
- add a short runbook for local verification
- document env and commands

Deliver:

- smoke test path
- operator notes
- final file list and verification steps

## Required Output Format After Every Iteration

At the end of each iteration, answer using this structure:

```text
Iteration completed: <number and name>

What I changed:
- ...

Files touched:
- ...

Commands/tests run:
- ...

Assumptions/blockers:
- ...

Waiting for confirmation before starting the next iteration.
```

## Start Command

Start now with `Iteration 0` only.

Do not implement `Iteration 1+` yet.
