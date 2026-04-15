# Publisher Service

## Responsibility

`Publisher Service` owns:

- polling unpublished rows from `publication_outbox`
- leasing/claiming rows safely
- publishing contract messages to RabbitMQ
- publishing without runtime topology ownership in the hardened stack
- recording `publication_attempts`
- marking rows `published`, `retryable`, or `failed`

## It does not own

- spider execution
- scraping logic
- store selectors
- CRM communication
- downstream processing after RabbitMQ

## Current implementation anchor

Current runtime modules:

- `services/publisher/main.py`
- `services/publisher/config.py`
- `services/publisher/outbox_reader.py`
- `services/publisher/rabbit_publisher.py`
- `services/publisher/publication_worker.py`

Compatibility wrappers still exist in `application/publisher/*`, but the standalone publisher runtime is now owned here.

## Observability and smoke

Publisher runtime now emits structured `publisher_event` logs through
`infrastructure/observability/event_logger.py`.

High-signal message codes:

- `PUBLISHER_CONNECT_FAILED`
- `PUBLISHER_PUBLISH_RETRY`
- `PUBLISHER_MESSAGE_FAILED`
- `PUBLISHER_BATCH_COMPLETED`
- `PUBLISHER_RUN_FAILED`
- `PUBLISHER_SMOKE_COMPLETED`
- `PUBLISHER_SMOKE_FAILED`

Fast broker validation:

- `python -m scripts.bootstrap_rabbitmq`
- `python -m scripts.rabbit_smoke`
- `python -m services.publisher.main --once`
