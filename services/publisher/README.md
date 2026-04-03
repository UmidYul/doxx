# Publisher Service

## Responsibility

`Publisher Service` owns:

- polling unpublished rows from `publication_outbox`
- leasing/claiming rows safely
- publishing contract messages to RabbitMQ
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
