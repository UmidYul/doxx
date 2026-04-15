# Publisher Service

## Scope

`Publisher Service` is a standalone service that reads `publication_outbox` rows from the scraper DB and publishes them to RabbitMQ.

Runtime boundary:

`Scraper Service -> Scraper DB -> Publisher Service -> RabbitMQ`

The scraper does not publish from spider code.

## Service Layout

- [main.py](/C:/Users/Lenovo/Desktop/doxx/services/publisher/main.py)
  CLI entrypoint for one-shot or continuous publisher runs.
- [config.py](/C:/Users/Lenovo/Desktop/doxx/services/publisher/config.py)
  Publisher-specific runtime configuration assembled from shared settings.
- [outbox_reader.py](/C:/Users/Lenovo/Desktop/doxx/services/publisher/outbox_reader.py)
  Claims outbox rows and marks them `published`, `retryable`, or `failed`.
- [rabbit_publisher.py](/C:/Users/Lenovo/Desktop/doxx/services/publisher/rabbit_publisher.py)
  Connects with publisher confirms and publishes persistent messages. In the hardened stack it does not declare topology.
- [publication_worker.py](/C:/Users/Lenovo/Desktop/doxx/services/publisher/publication_worker.py)
  Batch worker that connects outbox claiming, Rabbit publish, retry logic, and attempt logging.

Compatibility wrappers remain in `application/publisher/*`, but the active service implementation now lives under `services/publisher/`.

## How it works

1. `PublicationWorker` asks `SQLiteOutboxReader` for a claimed batch of rows with status `pending` or `retryable`.
2. Claiming sets outbox state to `publishing` with a lease.
3. Each claimed row is converted to the RabbitMQ event contract.
4. `RabbitMQPublisher` opens a robust RabbitMQ connection with heartbeat + connection name and gets the pre-created exchange.
5. The message is published with persistent delivery mode.
6. On success:
   - `publication_outbox.status = published`
   - `publication_outbox.published_at` is set
   - `publication_attempts` gets a success row
7. On failure:
   - `publication_outbox.retry_count` increments
   - `publication_outbox.last_error` is stored
   - `publication_outbox.available_at` is pushed forward with backoff
   - `publication_outbox.status` becomes `retryable` or `failed`
   - `publication_attempts` gets a failure row

## RabbitMQ Contract

The publisher sends a durable message with:

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

Topology:

- exchange: `RABBITMQ_EXCHANGE`
- queue: `RABBITMQ_QUEUE`
- CRM queue: `RABBITMQ_CRM_QUEUE`
- routing key: `RABBITMQ_ROUTING_KEY`
- topology bootstrap: `python -m scripts.bootstrap_rabbitmq`
- publisher runtime declare mode: `RABBITMQ_DECLARE_TOPOLOGY=false`
- message delivery mode: `persistent`

## Retry and Failure Discipline

- Only `pending` and `retryable` rows are claimable.
- Retry count is bounded by `SCRAPER_OUTBOX_MAX_RETRIES`.
- Backoff uses `SCRAPER_OUTBOX_RETRY_BASE_SECONDS`.
- Rows that exceed retry policy end in explicit DB state `failed`.
- This stage relies on the DB `failed` state as the terminal dead-letter discipline; no downstream consumer logic is required.

## Idempotent-ish Publication Discipline

- One outbox row owns one stable `event_id`.
- Retries never generate a new event id.
- Published rows are not re-claimed because status is explicit.
- Repeated retries are controlled by `available_at`, `retry_count`, and the lease window.

## Why this is better than publishing from spider code

- scraping stays decoupled from broker availability
- failed RabbitMQ publishes do not lose scraped products
- retry state becomes durable and observable
- attempt history is queryable
- replay can happen from DB without re-scraping the store
- scraper responsibility cleanly ends at RabbitMQ instead of leaking transport logic into spiders

## Observability

The publisher now emits structured `publisher_event` records for the highest-value
operational transitions instead of relying only on plain logger strings.

Primary signals:

- `PUBLISHER_CONNECT_FAILED`
- `PUBLISHER_PUBLISH_RETRY`
- `PUBLISHER_MESSAGE_FAILED`
- `PUBLISHER_BATCH_COMPLETED`
- `PUBLISHER_RUN_FAILED`
- `PUBLISHER_SMOKE_COMPLETED`
- `PUBLISHER_SMOKE_FAILED`

These events are wired into in-process observability counters, which makes local
smoke checks and broker triage easier to interpret.

## Recommended operator checks

1. Bootstrap topology when the environment is fresh:
   - `python -m scripts.bootstrap_rabbitmq`
2. Validate publish, retry lane, and DLQ wiring:
   - `python -m scripts.rabbit_smoke`
3. Run one publisher batch against the current scraper DB:
   - `python -m services.publisher.main --once`
