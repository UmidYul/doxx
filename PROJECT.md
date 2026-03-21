# MOSCRAPER PROJECT

## Overview

Moscraper is a **stateless** scraping service.

Its only responsibility is:

- scrape product/listing data from source websites,
- apply **minimal deterministic** normalization,
- validate outbound event payloads (Pydantic v2),
- publish events to **RabbitMQ** (CloudEvents-compatible JSON, `orjson`, **aio-pika** with publisher confirms).

Moscraper does **not** own business state.

The CRM platform is the system of record and is fully responsible for:

- full normalization and semantic enrichment,
- deduplication and idempotency (**`entity_key` + `payload_hash`**),
- image downloading and storage,
- persistence to database,
- retries, dead-letter handling, and downstream processing.

## Target architecture

```
Store websites
  → Moscraper (Scrapy)
  → RabbitMQ (topic exchange, routing e.g. listing.scraped.v1)
  → CRM ingestion consumer
  → CRM normalization / storage / media / DB
```

**Topology note:** Moscraper may **declare the durable topic exchange** it publishes to (safe for producers). **Quorum queues and bindings** to that exchange are owned by **CRM / integration infrastructure**, not by this scraper. Published messages must remain **compatible** with quorum queues (persistent delivery, etc.).

## Explicit non-goals

Moscraper must **not**:

- use its own database,
- maintain parse cache or pending-event tables,
- store product images or raw HTML archives,
- perform LLM-heavy or full business normalization (no LLM cascade in baseline),
- compare against its own historical state for deltas,
- send listings to CRM over **REST**,
- own retry persistence when the broker rejects a publish.

## scrapy-playwright (optional)

- **Not** part of the default baseline: core settings use plain HTTP download handlers.
- Install: `pip install '.[playwright]'` and `playwright install`.
- Use **scrapy-playwright only** for SPA / dynamic sites that cannot be scraped reliably with static HTML extraction.
- Opt in **per spider** via `custom_settings` (Playwright download handlers + request `meta`), not globally for all spiders.

## Core runtime responsibilities

Moscraper does:

- extraction in spiders,
- price / currency / boolean normalization and light title cleanup,
- preserving `raw_specs` and `description` as CRM input,
- building the CloudEvents envelope and publishing to RabbitMQ.

## Message contract

Envelope (CloudEvents-compatible):

| Field | Role |
|--------|------|
| `specversion` | `"1.0"` |
| `id` | UUID per publish |
| `source` | `moscraper://{store}` |
| `type` | `com.moscraper.listing.scraped` |
| `time` | UTC timestamp |
| `datacontenttype` | `application/json` |
| `subject` | `listing` |
| `data` | business payload |

`data` includes at minimum: `schema_version`, `entity_key`, `payload_hash`, `store`, `url`, `title`, `scraped_at`, plus optional price, stock, brand, `raw_specs`, `description`, `image_urls` (see `domain/messages.py`).

## Delivery model

- **Client:** aio-pika  
- **Confirms:** publisher confirms required on the RabbitMQ publisher channel  
- **Persistence:** persistent messages  
- **Semantics:** at-least-once; CRM must treat duplicates safely  

If publish fails: **fail the run** — no local disk or DB buffer (except `MOSCRAPER_DISABLE_PUBLISH` for automated tests only).

## Integration boundary

Moscraper knows only the **message contract** and **broker settings**. It does not know CRM tables, media layout, or dedup storage.

## Configuration template

See **`.env.example`** (single template file for the repo).
