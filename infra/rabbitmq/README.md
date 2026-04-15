# RabbitMQ Topology

RabbitMQ is the durable boundary for the active contour:

`scraper -> scraper DB -> outbox -> publisher -> RabbitMQ -> CRM`

## Source Of Truth

- runtime topology bootstrap: `scripts/bootstrap_rabbitmq.py`
- human-readable contract: `infra/rabbitmq/topology.json`
- publisher behavior: `services/publisher/rabbit_publisher.py`
- payload contract: `shared/contracts/scraper_product_event.schema.json`

`definitions.json` is intentionally not used anymore. Topology is now created idempotently via the management API so credentials and retry TTLs come from env instead of being hardcoded in repo JSON.

The bootstrap supports two runtime modes:

- local/full-control RabbitMQ: manages vhost, users, permissions, exchanges, queues, and bindings
- hosted shared/free RabbitMQ: manages only exchanges, queues, and bindings when `RABBITMQ_BOOTSTRAP_MANAGE_VHOST=false`, `RABBITMQ_BOOTSTRAP_MANAGE_USERS=false`, and `RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS=false`

## Runtime Contract

- vhost: `moscraper` locally, or the provider-issued vhost on hosted shared/free plans
- producer exchange: `moscraper.events` (`topic`)
- scraper-owned queue: `scraper.products.v1`
- CRM ingress queue: `crm.products.import.v1`
- retry exchange: `crm.products.retry`
- requeue exchange: `crm.products.requeue`
- terminal DLX: `crm.products.dlx`
- routing key: `listing.scraped.v1`

Retry lanes:

- `crm.products.import.v1.retry.30s`
- `crm.products.import.v1.retry.5m`
- `crm.products.import.v1.retry.30m`
- `crm.products.import.v1.dlq`

## Ownership

The scraper side owns:

- outbox persistence and stable `event_id`
- publish to `moscraper.events`
- scraper audit queue `scraper.products.v1`
- operator bootstrap of the shared local topology

The CRM side owns:

- business processing of `crm.products.import.v1`
- manual `ack`
- retry policy usage through `crm.products.retry`
- DLQ triage of `crm.products.import.v1.dlq`

Important nuance:

- `crm.products.import.v1` is pre-created by this repo for local interoperability;
- business ownership still remains CRM-side;
- `publication.queue_name` inside the event stays `scraper.products.v1` and is not the CRM queue.
