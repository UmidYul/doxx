# Store playbook: texnomart

## Summary

- **Spider:** `texnomart` in `infrastructure/spiders/texnomart.py`
- **Host:** `texnomart.uz`
- **Access mode:** browser-assisted crawl for current storefront stability
- **Reference basis:** old `E-katalog` Texnomart family plus current resilient selectors

Texnomart now follows the same ingestion contour as MediaPark:

`listing -> PDP -> minimal structuring -> scraper DB -> outbox`

## Listing flow

- Seeds come from `start_category_urls()`.
- Listing discovery looks for `/product/`, `/catalog/product/`, and related product-detail URLs in anchors and inline HTML payloads.
- Nested categories are discovered from `/katalog/` and `/catalog/` links, but traversal stays constrained to phone-oriented paths.
- Pagination prefers explicit next links and falls back to synthetic `page=` mutation when product tiles are present.

## PDP flow

- PDP recognition is path-based.
- `source_id` prefers structured identifiers from the query string, then numeric path suffixes, then the last slug segment.
- Title, brand, price, stock, description, images, and raw specs are extracted with JSON-LD-first logic plus HTML fallbacks.
- The spider emits raw product snapshots only; persistence and publication are handled outside the spider.

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

## Extraction strategy

- **Source discovery:** listing anchors and serialized product hrefs in page source
- **Price:** main PDP price block first, then JSON-LD `offers.price`, then inline currency text
- **Stock:** JSON-LD availability and text fallback
- **Specs:** JSON-LD `additionalProperty`, tables, `dl`, characteristic rows
- **Images:** JSON-LD images and `img` attrs
- **Category hint:** lightweight URL/title classifier

## Known brittle points

- Texnomart storefront markup changes more often than MediaPark, so product URL patterns must stay defensive.
- Installment-price widgets can look like the main price if selectors become too broad.
- Category navigation can surface non-phone branches unless traversal stays narrowly filtered.

## Store-specific tuning still expected

- browser necessity on live pages
- price selector drift between retail and installment blocks
- category-path allowlist refinement if the phone tree changes

## Intentionally left downstream

- typed spec normalization
- canonical model inference
- CRM event shaping

## Acceptance / ops

- Fixture acceptance: `tests/acceptance/test_store_acceptance.py`
- Cross-store ingestion matrix: `tests/acceptance/test_store_ingestion_matrix.py`
- Texnomart is the second reference migration after MediaPark and usually needs live tuning around markup drift rather than architecture changes.
