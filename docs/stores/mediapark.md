# Store playbook: mediapark

## Summary

- **Spider:** `mediapark` in `infrastructure/spiders/mediapark.py`
- **Host:** `mediapark.uz`
- **Access mode:** HTTP-first, no browser required in the normal path
- **Reference basis:** old `E-katalog` MediaPark parser
- **Role in `doxx`:** reference implementation for the unified ingestion contour

Deep dive: [`mediapark_new.md`](mediapark_new.md).

## Listing flow

- Category seeds come from `start_category_urls()`.
- Listing discovery scans anchors plus escaped inline payloads for `/products/view/...` URLs.
- Nested category traversal follows `/products/category/...` hubs, but stays constrained to the target phone family.
- Pagination is synthetic and defensive: the spider mutates `page=` and stops on repeated empty or duplicate listings.

## PDP flow

- PDP recognition is path-based and rejects obvious deleted pages.
- `source_id` is extracted from the trailing numeric slug in the URL.
- Title, brand, price, stock, description, images, and specs are filled with layered extraction instead of one brittle selector.
- The spider yields only minimally structured raw product data to the persistence pipeline.

## What gets saved

- `store_name`
- `source_id`
- `source_url`
- `title`
- `brand`
- `price_raw`
- `in_stock`
- `description`
- `raw_specs`
- `image_urls`
- `category_hint`

Persistence then writes the item into `raw_products`, `raw_product_images`, `raw_product_specs`, and creates a `publication_outbox` row.

## Extraction strategy

- **Source discovery:** regex-friendly HTML and embedded Next.js payloads
- **Price:** JSON-LD `offers.price`, meta tags, inline price payload fallback
- **Stock:** JSON-LD `availability`, then text fallback
- **Specs:** `__next_f`, `__NEXT_DATA__`, JSON-LD `additionalProperty`, tables, and body-text heuristics
- **Images:** JSON-LD, Next.js payloads, `og:image`, and `img` attributes
- **Category hint:** lightweight classifier only

## Source Of Truth Order

MediaPark stays closest to the old `E-katalog` behavior by preferring stable embedded data before brittle DOM text:

1. listing discovery from inline HTML / escaped script payloads for `/products/view/...`
2. `source_id` from the trailing numeric PDP slug
3. Product JSON-LD for title, price, stock, description, brand, and base images
4. Next.js payloads (`__next_f`, `__NEXT_DATA__`) for raw specs and extra images
5. DOM tables / body text as fallback only when structured payloads are incomplete

This keeps scraper output raw and store-native while avoiding deep normalization.

## Known brittle points

- MediaPark periodically changes Next.js payload shape.
- Partial PDP renders can hide specs until later in the DOM or embedded scripts.
- Russian and Latin spec labels are mixed, so raw fidelity is more important than aggressive normalization inside the scraper.

## Intentionally left downstream

- typed normalization
- canonical model matching
- cross-store merge logic
- CRM contract shaping

## Acceptance / ops

- Fixture acceptance: `tests/acceptance/test_mediapark_new_flow.py`
- Cross-store ingestion matrix: `tests/acceptance/test_store_ingestion_matrix.py`
- Reference status: MediaPark is the baseline store to compare future migrations against.

Bounded QA run:

```powershell
$env:SCRAPER_DB_PATH='data/scraper/qa/mediapark_qa.db'
.\.venv\Scripts\python.exe -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5 -s CLOSESPIDER_PAGECOUNT=25 -L INFO
```

What to verify after the run:

- rows exist in `raw_products`
- matching `raw_product_specs` and `raw_product_images` rows exist
- `publication_outbox` rows were created
- `scrape_run_summary` reports non-zero persisted items with non-zero specs/image coverage
