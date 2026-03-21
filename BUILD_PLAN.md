# BUILD PLAN — MOSCRAPER (RABBITMQ + CLOUDEVENTS)

## FOUNDATION PROMPT (исполнитель / AI)

Собери **stateless** скрапер на Scrapy: данные с сайтов → минимальная детерминированная нормализация → валидация Pydantic v2 → **публикация** JSON-сообщений в **RabbitMQ**. Каждое исходящее сообщение — это **CloudEvents**-совместимый конверт (`specversion`, `id`, `source`, `type`, `time`, `data`) и полезная нагрузка в `data` (в т.ч. `entity_key`, `payload_hash`, `schema_version`). Интеграция с CRM — **только через брокер**; прямые HTTP-синхронизации в CRM, отдельная БД скрапера и доставка через сторонние воркеры задач вместо брокера не используются. Реализуй **`PublishPipeline`**: на каждый item строит событие и отправляет его через **aio-pika** с **publisher confirms** и **persistent** сообщениями. Очереди и привязки под потребителя объявляет CRM (или интеграционный слой), не скрапер — скрапер может объявить только **durable topic exchange**, в который публикует.

---

## Foundation rules (English summary)

Target flow:

```
source websites → stateless Moscraper (Scrapy) → RabbitMQ → CRM consumer
```

Do **not** implement:

- scraper-owned SQL database or third-party BaaS used as this service’s system of record  
- local tables or disk-backed queues for “unsent” listings between runs  
- comparing crawls to historical state stored inside the scraper  
- image **storage** or long-term raw HTML archives in the scraper  
- HTTP/REST push of listings directly to CRM APIs  
- task-queue workers or a secondary broker used *instead of* RabbitMQ for CRM handoff  
- LLM / AI enrichment in the baseline scraping pipeline  

## Mandatory stack

- Python 3.11+  
- Scrapy  
- **RabbitMQ** (broker)  
- **aio-pika** (async client, **publisher confirms**)  
- **Pydantic v2** (envelope + `data`)  
- **orjson** (serialization)  

## Optional stack (per spider only)

- **scrapy-playwright** — extra `pip install '.[playwright]'`; use only for SPA/JS-heavy stores via **per-spider** `custom_settings`. Default project settings must not require Playwright.

## Required components

| Area | Module / role |
|------|----------------|
| Contract | `domain/messages.py` — Pydantic models for **CloudEvents** + `data` |
| Builder | `application/message_builder.py` — `entity_key`, `payload_hash`, envelope |
| Publisher API | `infrastructure/publishers/base.py` |
| Broker client | `infrastructure/publishers/rabbitmq_publisher.py` — connect, channel, confirms, durable exchange, **publish** |
| Factory | `infrastructure/publishers/publisher_factory.py` |
| **PublishPipeline** | `infrastructure/pipelines/publish_pipeline.py` — receives normalized items, builds message, calls publisher |
| Settings | `config/settings.py` — broker URL, exchange, routing key, runtime flags only |
| Scrapy wiring | `config/scrapy_settings.py` — `ITEM_PIPELINES`: validate → normalize → **publish** |

## Build phases (ordered)

Use these as implementation milestones; each phase should be committable and testable.

1. **Contract** — Define CloudEvents-compatible models and `data` schema in `domain/messages.py`; document `schema_version`, `entity_key`, `payload_hash`.  
2. **Message builder** — Implement stable hashing and envelope assembly in `application/message_builder.py`.  
3. **Broker settings** — Add `config/settings.py` fields: broker URL, exchange name, routing key, optional TLS; single **`.env.example`** template.  
4. **RabbitMQ publisher** — `rabbitmq_publisher.py`: declare durable **topic exchange** (if policy allows), create channel with **publisher confirms**, publish **persistent** messages; on failure raise (fail fast).  
5. **PublishPipeline** — Scrapy pipeline: from item → `message_builder` → `publisher.publish`; close publisher on spider idle/close.  
6. **Pipeline order** — `scrapy_settings.py`: Validate → Normalize → Publish; no image/delta/global Playwright in defaults.  
7. **Docker / broker** — `docker-compose.yml`: RabbitMQ service (e.g. 5672, management 15672); scraper service runs `scrapy crawl …`. Do not declare CRM ingestion queues in scraper compose unless CRM explicitly requires it.  
8. **Tests** — `MOSCRAPER_DISABLE_PUBLISH=true` for unit tests (no TCP to broker); tests for `entity_key` / `payload_hash` stability and pipeline behavior.  

## PublishPipeline behavior (checklist)

- [ ] Runs after validate + normalize pipelines.  
- [ ] Uses async publisher from Twisted/async bridge (or equivalent) without blocking the reactor incorrectly.  
- [ ] Each successfully validated listing yields **one** publish attempt per item (at-least-once toward broker; CRM dedupes).  
- [ ] Logs broker errors clearly; does not write failed messages to a local store.  

## RabbitMQ setup (scraper side)

- [ ] Environment variables documented in `.env.example` (URI, exchange, routing key).  
- [ ] Exchange: durable, type appropriate for routing (typically **topic**).  
- [ ] Messages: `delivery_mode=persistent` (or equivalent).  
- [ ] **Publisher confirms** enabled before treating publish as success.  
- [ ] Quorum queues, bindings, DLQ — **CRM / ops** responsibility unless agreed otherwise.  

## Normalization policy

**Deterministic only:**

- parse price → internal float / published integer as per contract  
- currency default (`DEFAULT_CURRENCY`)  
- booleans / `in_stock`  
- light title / brand cleanup (`unit_normalizer` where used)  
- pass through `raw_specs`, `description`, `image_urls`  

CRM owns semantic normalization and LLM.

## Failure policy

- Broker publish failure → **fail the run** (no scraper-owned backlog table or disk queue).  
- Re-runs are safe if CRM implements **`entity_key` + `payload_hash`** idempotency.  

## Contract policy

Every outbound message must:

- validate through Pydantic v2  
- use the CloudEvents-compatible envelope  
- include `schema_version`, `entity_key`, `payload_hash` in `data`  

## Environment template

- Single file: **`.env.example`** — no duplicate `env.example`.  

## Tests

- `MOSCRAPER_DISABLE_PUBLISH=true` — tests only; still build and validate messages, skip live **RabbitMQ** TCP.  
- Unit tests for `entity_key` and `payload_hash` (`tests/unit/test_message_builder.py` and related).  

## AI execution rule

Any implementation from this plan must preserve:

- stateless scraper  
- **RabbitMQ** as the only integration path to CRM for listing events  
- **CloudEvents**-compatible **публикация**  
- no scraper-owned durable storage for listings  
- CRM-owned state, retries after consume, DLQ  

If legacy code suggests HTTP sync to CRM, image persistence, or DB-backed scrape queues in the scraper, remove or replace it.
