# MediaPark New Scraper

## Purpose

This document describes the MediaPark scraper after the stage-3 migration onto the new scraper architecture:

`listing -> PDP -> minimal structuring -> scraper DB -> outbox`

It is the reference implementation for store migrations that follow the old `E-katalog` scraping style while stopping at the new scraper-side boundary.

## Why this follows the old reference

The implementation in [mediapark.py](/C:/Users/Lenovo/Desktop/doxx/infrastructure/spiders/mediapark.py) intentionally mirrors the old `E-katalog` MediaPark parser in the places that mattered most for stability:

- synthetic pagination instead of trusting only HTML next buttons
- regex-driven listing discovery for `/products/view/...`
- narrow category-hub traversal for MediaPark smartphone listings
- `source_id` extraction from the PDP slug
- JSON-LD-first PDP parsing for title, price, stock, brand, description, and images
- layered raw-spec extraction from `__next_f`, `__NEXT_DATA__`, JSON-LD `additionalProperty`, tables, and body text
- lightweight category hinting only

What was intentionally **not** ported from the old project:

- AI enrichment
- typed spec normalization as the main output
- variant building
- CRM payload shaping
- downstream merge logic

## Listing Flow

1. Seeds come from `start_category_urls()`.
2. Listing discovery scans the HTML and escaped script payloads for product URLs matching `/products/view/...`.
3. Nested MediaPark category hubs are discovered from `/products/category/...` links, but only for the targeted smartphone hub family.
4. Pagination is synthetic: page `N+1` is built by mutating the query string, just like the old parser approach.
5. Pagination stops on:
   - no next URL
   - `12` pages reached
   - `2` empty listing repeats
   - `2` duplicate listing signature repeats

## PDP Flow

1. Reject obvious missing-product pages and `4xx` PDP responses.
2. Parse Product JSON-LD first.
3. Extract `source_id` from the URL slug.
4. Fill minimal fields:
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
5. Yield only minimally structured raw scraper data to the persistence pipeline.

## Extraction Methods

### Listing discovery

- HTML anchors
- escaped product URLs inside inline scripts
- strict `/products/view/<slug>-<id>` matching

### Source id

- extracted from the trailing numeric slug in the PDP URL
- fallback to the last path segment only if the numeric slug is absent

### Title

- JSON-LD `name`
- `og:title`
- `h1`

### Price

- JSON-LD `offers.price`
- `product:price:amount`
- inline `"price"` payload fallback

### Stock

- JSON-LD `offers.availability`
- text-based out-of-stock fallback patterns

### Raw specs

- `self.__next_f.push(...)` chunks
- `__NEXT_DATA__`
- JSON-LD `additionalProperty`
- table rows
- body text after spec section headers

### Images

- JSON-LD `image`
- `__NEXT_DATA__` image candidates
- image tag attributes
- `og:image`

### Category hint

- lightweight `classify_category(...)`
- no typed normalization
- no canonical model inference

## Observability

MediaPark now contributes the following run-level signals through the crawl registry and scrape-run stats:

- listing pages visited
- product pages visited
- scraped items count
- failed PDP count
- persisted items count
- products with specs / without specs
- products with images / without images
- spec coverage ratio
- image coverage ratio

The persistence pipeline logs a final `scrape_run_summary` with these values when the spider closes.

## Known Brittle Points

- MediaPark still exposes product data through changing Next.js payload shapes, so `__next_f` and `__NEXT_DATA__` parsing must stay defensive.
- Some categories surface partial PDP content first and rely on delayed sections for specs.
- Product pages can carry mixed Russian and Latin labels, so raw specs must remain source-faithful instead of aggressively normalized in the scraper.
- Brand-category hubs can change slugs over time; the spider should be updated if MediaPark renames those categories.

## What stays in the scraper layer

- crawl stability
- field extraction
- minimal packaging
- raw fidelity
- durable persistence

## What is intentionally left to the CRM normalization layer

- typed spec normalization
- canonical model matching
- cross-store merge logic
- business-facing product identity decisions
- CRM contract shaping

This is what makes MediaPark the right reference implementation for the next store migrations: the scraper solves scraping well, preserves raw truth well, and stops at the DB/outbox boundary.
