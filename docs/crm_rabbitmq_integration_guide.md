# CRM RabbitMQ Integration Guide

## Active Boundary

Active runtime flow:

`spider -> scraper DB -> publication_outbox -> publisher service -> RabbitMQ -> CRM consumer`

Only one sender reaches the CRM boundary:

- `services/publisher/publication_worker.py`
- `services/publisher/rabbit_publisher.py`

The active payload contract is `ScraperProductEvent` from `domain/publication_event.py`, not the legacy CloudEvent shape and not the legacy CRM HTTP sync envelope.

## Source Of Truth

Use these files in this order:

1. `scripts/bootstrap_rabbitmq.py`
2. `services/publisher/rabbit_publisher.py`
3. `services/publisher/publication_worker.py`
4. `infrastructure/persistence/sqlite_store.py`
5. `application/ingestion/event_builder.py`
6. `domain/publication_event.py`
7. `shared/contracts/scraper_product_event.schema.json`
8. `infra/rabbitmq/topology.json`

## Broker Topology

RabbitMQ topology is bootstrapped idempotently with:

```powershell
python -m scripts.bootstrap_rabbitmq
```

Or automatically in Docker through the `rabbitmq-bootstrap` compose service.

Default topology:

- vhost: `moscraper` for the local Docker broker, or the provider-supplied vhost for hosted shared/free RabbitMQ
- producer exchange: `moscraper.events` (`topic`)
- scraper audit queue: `scraper.products.v1`
- CRM ingress queue: `crm.products.import.v1`
- retry exchange: `crm.products.retry`
- requeue exchange: `crm.products.requeue`
- terminal DLX: `crm.products.dlx`
- retry queues:
  - `crm.products.import.v1.retry.30s`
  - `crm.products.import.v1.retry.5m`
  - `crm.products.import.v1.retry.30m`
- quarantine queue: `crm.products.import.v1.dlq`

Bindings:

- `moscraper.events -> scraper.products.v1` with `listing.scraped.v1`
- `moscraper.events -> crm.products.import.v1` with `listing.scraped.v1`
- `crm.products.retry -> *.retry.*` with `30s`, `5m`, `30m`
- retry queues dead-letter into `crm.products.requeue` with `main`
- `crm.products.requeue -> crm.products.import.v1` with `main`
- `crm.products.import.v1` dead-letters into `crm.products.dlx` with `dead`
- `crm.products.dlx -> crm.products.import.v1.dlq` with `dead`

Important nuance:

- this repo operator-creates `crm.products.import.v1` for local interoperability;
- CRM still owns the business semantics of that queue;
- `publication.queue_name` inside the message remains `scraper.products.v1` and is not the CRM queue.

## Credentials And Access

Broker roles:

- `RABBITMQ_ADMIN_USER` / `RABBITMQ_ADMIN_PASS`: bootstrap and management UI
- `RABBITMQ_PUBLISHER_USER` / `RABBITMQ_PUBLISHER_PASS`: publish-only to `moscraper.events`
- `RABBITMQ_CRM_USER` / `RABBITMQ_CRM_PASS`: consume CRM queue and publish to `crm.products.retry`

Hosted shared/free nuance:

- providers such as CloudAMQP Little Lemur typically give you one pre-created vhost and one credential pair
- in that mode, set `RABBITMQ_ADMIN_*`, `RABBITMQ_PUBLISHER_*`, and `RABBITMQ_CRM_*` to the provider values or set `RABBITMQ_CRM_URL` explicitly
- set `RABBITMQ_BOOTSTRAP_MANAGE_VHOST=false`
- set `RABBITMQ_BOOTSTRAP_MANAGE_USERS=false`
- set `RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS=false`

Default env names:

- `RABBITMQ_URL`
- `RABBITMQ_CRM_URL`
- `RABBITMQ_MANAGEMENT_URL`
- `RABBITMQ_VHOST`
- `RABBITMQ_EXCHANGE`
- `RABBITMQ_QUEUE`
- `RABBITMQ_CRM_QUEUE`
- `RABBITMQ_RETRY_EXCHANGE`
- `RABBITMQ_REQUEUE_EXCHANGE`
- `RABBITMQ_DLX_EXCHANGE`
- `RABBITMQ_ROUTING_KEY`
- `RABBITMQ_DECLARE_TOPOLOGY`
- `RABBITMQ_HEARTBEAT_SECONDS`
- `RABBITMQ_CONNECTION_NAME`
- `RABBITMQ_BOOTSTRAP_MANAGE_VHOST`
- `RABBITMQ_BOOTSTRAP_MANAGE_USERS`
- `RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS`

Network posture:

- AMQP is exposed to LAN on `5672`
- management UI is bound locally only on `127.0.0.1:15672`

## Publisher Runtime Behavior

Publisher behavior confirmed in `services/publisher/rabbit_publisher.py`:

- uses `aio_pika.connect_robust`
- sends heartbeat and connection name
- uses publisher confirms
- publishes persistent JSON messages
- with `RABBITMQ_DECLARE_TOPOLOGY=false`, does not declare exchange/queues/bindings at runtime

This allows the publisher account to stay least-privileged.

## Message Contract

Required top-level fields:

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

Active `event_type`:

- `scraper.product.scraped.v1`

Required `structured_payload` fields:

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

Important edge-cases CRM must support:

- `source_id` can be `null`
- when `source_id` is `null`, `identity_key` is derived from canonical URL and remains stable
- `raw_specs` is dynamic and can contain nested objects or arrays
- publisher retries do not change `event_id`
- `publication` is delivery metadata only, not product business state

## Recommended CRM Consumer Rules

Validate:

- `content_type == application/json`
- `message_id == event_id`
- `type == event_type`
- `event_type == scraper.product.scraped.v1`
- `schema_version == 1`
- top-level values match duplicates inside `structured_payload`

Persist before `ack`:

- raw inbound body
- parsed payload
- AMQP metadata
- `event_id`
- `payload_hash`
- `structured_payload.identity_key`
- processing status

Idempotency:

- primary key: `event_id`
- business safety key: `structured_payload.identity_key + payload_hash`

Retry discipline:

- on transient failure, publish to `crm.products.retry` with routing key `30s`, `5m`, or `30m`, then `ack` the original
- on permanent failure, reject to DLQ / quarantine
- do not create infinite requeue loops

## Minimal Local Runbook

On the scraper laptop:

```powershell
docker compose up -d rabbitmq
python -m scripts.bootstrap_rabbitmq
python -m scripts.rabbit_smoke
```

For the CRM laptop consumer, connect with local broker values:

```env
CRM_RABBITMQ_URL=amqp://moscraper_crm:<crm-pass>@<SCRAPER_LAN_IP>:5672/moscraper
CRM_RABBITMQ_QUEUE=crm.products.import.v1
CRM_RABBITMQ_RETRY_EXCHANGE=crm.products.retry
CRM_RABBITMQ_RETRY_KEY_30S=30s
CRM_RABBITMQ_RETRY_KEY_5M=5m
CRM_RABBITMQ_RETRY_KEY_30M=30m
```

For hosted shared/free RabbitMQ, both laptops use the provider AMQPS URL instead of a LAN IP:

```env
CRM_RABBITMQ_URL=amqps://provider-user:provider-pass@provider-host/provider-vhost
CRM_RABBITMQ_QUEUE=crm.products.import.v1
CRM_RABBITMQ_RETRY_EXCHANGE=crm.products.retry
CRM_RABBITMQ_RETRY_KEY_30S=30s
CRM_RABBITMQ_RETRY_KEY_5M=5m
CRM_RABBITMQ_RETRY_KEY_30M=30m
```

Do not consume `scraper.products.v1` from CRM.
