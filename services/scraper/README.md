# Scraper Service

## Responsibility

`Scraper Service` owns:

- store spiders
- listing -> PDP traversal
- store-specific selectors
- source/external id extraction
- raw specs extraction
- image extraction
- basic category hinting
- minimal structuring only
- durable write into `Scraper DB`
- creation of `publication_outbox` rows

## It does not own

- direct CRM delivery
- deep normalization
- canonical matching
- product merge across stores
- downstream business workflows after RabbitMQ

## Current implementation anchor

The repo still contains runtime code under legacy package roots, but the logical stage-1 service boundary maps to:

- spiders: `infrastructure/spiders/`
- save-to-db pipeline: `infrastructure/pipelines/scraper_storage_pipeline.py`
- persistence adapter: `infrastructure/persistence/sqlite_store.py`
- raw snapshot model: `domain/scraped_product.py`

## Migration note

`MediaPark`, `Texnomart`, and `Alifshop` now use old `E-katalog` store logic as the main scraping reference, but stop at the new DB/outbox boundary.
`Uzum` follows the same persistence and publication contract, while keeping its own browser-first scraping behavior because there is no old `E-katalog` counterpart for it.
