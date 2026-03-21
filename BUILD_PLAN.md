# BUILD PLAN — MOSCRAPER RABBITMQ FLOW

## Foundation rules

Build only:

```
source websites → stateless Moscraper (Scrapy) → RabbitMQ → CRM
```

Do **not** implement:

- scraper-owned DB, parse_cache, pending_events  
- delta detection against local state  
- image **storage** or raw HTML archives in the scraper  
- REST synchronization to CRM  
- Celery/Redis (or any DB) as a delivery layer  
- LLM cascade / AI enrichment inside the scraping pipeline (baseline)  

## Mandatory stack

- Python 3.11+  
- Scrapy  
- RabbitMQ  
- aio-pika (publisher confirms)  
- Pydantic v2  
- orjson  

## Optional stack (per spider only)

- **scrapy-playwright** — optional extra `pip install '.[playwright]'`; use only for SPA/JS-heavy stores via **per-spider** `custom_settings`. Do not make the default project settings depend on Playwright.

## Required components

| Area | Module |
|------|--------|
| Contract | `domain/messages.py` — Pydantic models for CloudEvents + `data` |
| Builder | `application/message_builder.py` — `entity_key`, `payload_hash`, envelope |
| Publisher API | `infrastructure/publishers/base.py` |
| RabbitMQ | `infrastructure/publishers/rabbitmq_publisher.py` — aio-pika, confirms, durable exchange |
| Factory | `infrastructure/publishers/publisher_factory.py` |
| Pipeline | `infrastructure/pipelines/publish_pipeline.py` |
| Settings | `config/settings.py` — broker + runtime only |
| Scrapy | `config/scrapy_settings.py` — validate → normalize → publish |

## Normalization policy

**Deterministic only:**

- parse price → `price_value` where possible  
- currency default (`DEFAULT_CURRENCY`)  
- booleans / `in_stock`  
- light title cleanup  
- light brand cleanup (`unit_normalizer`)  
- pass through `raw_specs`, `description`, `image_urls` from the page  

CRM owns semantic normalization and LLM.

## Failure policy

- Broker publish failure → **fail the run** (no `pending_events`, no local queue).  
- Re-runs are safe if CRM implements **`entity_key` + `payload_hash`** idempotency.  

## Contract policy

Every outbound message must:

- validate through Pydantic v2  
- use the CloudEvents-compatible envelope  
- include `schema_version`, `entity_key`, `payload_hash`  

## Docker / broker

- Baseline `docker-compose.yml`: **RabbitMQ only** (management image optional).  
- **Do not** declare CRM quorum queues or bindings in scraper compose; that is CRM/integration ownership.  
- Scraper may declare the **topic exchange** it publishes to.  

## Environment template

- Single file: **`.env.example`** — remove any duplicate `env.example`.

## Tests

- `MOSCRAPER_DISABLE_PUBLISH=true` — **tests only**; skips TCP to RabbitMQ while still building messages.  
- Unit tests for `entity_key` and `payload_hash` stability (`tests/unit/test_message_builder.py`).  

## AI execution rule

Any implementation from this plan must preserve:

- stateless scraper  
- RabbitMQ-only integration to CRM  
- no storage inside scraper  
- CRM-owned state  

If old code suggests parse_cache, REST sync, or image persistence in the scraper, remove it.
