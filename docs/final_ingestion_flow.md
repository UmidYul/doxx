# Final Ingestion Flow

Stage 6 closes the mixed architecture and standardizes every active store on one ingestion contour:

`store spider -> scraper DB -> outbox -> publisher service -> RabbitMQ`

## Active services

`Scraper Service`

- owns store spiders
- owns listing traversal and PDP parsing
- performs only minimal structuring
- persists every scraped item into scraper DB
- creates outbox rows

`Publisher Service`

- claims `publication_outbox` rows
- publishes contract events to RabbitMQ
- records `publication_attempts`
- marks rows `published`, `retryable`, or `failed`

`RabbitMQ`

- is the final boundary of the scraper contour
- separates scraper-team responsibility from downstream consumers

## Active data flow

1. A store spider extracts a raw product snapshot.
2. `ScraperStoragePipeline` validates the item and sends it to `ScraperPersistenceService`.
3. Persistence writes:
   - `raw_products`
   - `raw_product_images`
   - `raw_product_specs`
   - `publication_outbox`
4. The standalone publisher claims pending outbox rows.
5. The publisher sends durable messages to RabbitMQ.
6. The publisher writes `publication_attempts` and updates publication status.

## What was removed or disabled from the active runtime

- `NormalizePipeline` is not part of Scrapy `ITEM_PIPELINES`
- `SyncPipeline` is not part of Scrapy `ITEM_PIPELINES`
- `PublishPipeline` is not part of Scrapy `ITEM_PIPELINES`
- scraper spiders do not call CRM transports directly
- publication is not done from spider code
- the duplicate unused Rabbit publisher under `infrastructure/publishers/` is removed

Legacy CRM and normalization code still exists in the repo for migration context and historical tests, but it is no longer the active ingestion path.

## Why this is now a clean architecture

- there is one persistence contract for every store
- there is one publication boundary for every store
- there is one service responsible for RabbitMQ publication
- scraping stability is separated from downstream business shaping
- replay, audit, XLSX export, and coverage analysis all work from durable scraper-side state

## Store status after stage 6

- `mediapark`: reference implementation, old-parser behavior preserved in the new contour
- `texnomart`: migrated onto the same contract, needs live-site tuning only
- `uzum`: browser-backed store aligned with the same contract
- `alifshop`: old-reference migration completed on the same contract

## Reference files

- `infrastructure/spiders/`
- `infrastructure/pipelines/scraper_storage_pipeline.py`
- `infrastructure/persistence/sqlite_store.py`
- `services/publisher/`
- `shared/contracts/`
- `shared/db/`
