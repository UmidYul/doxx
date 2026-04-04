# Store playbook: uzum

## Summary

- **Spider:** `uzum` in `infrastructure/spiders/uzum.py`
- **Host:** `uzum.uz`
- **Access mode:** Playwright-backed browser crawl
- **Reference basis:** no direct old `E-katalog` equivalent; migrated to the same raw-output contract used by the reference stores

Uzum follows the same ingestion boundary as the other stores:

`listing -> PDP -> minimal structuring -> scraper DB -> outbox`

## Listing flow

- The primary bounded-run seed is `https://uzum.uz/ru/category/smartfony-12690`.
- The spider opens category pages with Playwright and mirrors hydrated `/product/` anchors into a hidden DOM snapshot before Scrapy serializes `response.text`.
- It scrolls the page in controlled steps to surface lazy-loaded product tiles.
- Pagination is synthetic through the `page=` query parameter when an explicit next link is absent.
- Uzum-specific duplicate listing signatures intentionally ignore the `page` number. This stops bounded runs from burning through 10+ synthetic pages when Uzum serves the same 48-card shell behind different `page=` URLs.
- Category traversal stays restricted to electronics-friendly URLs through `is_electronics_category_url(...)`, then further narrows to high-value smartphone branches.
- Low-value / misleading phone branches like `smartfony-i-telefony-*`, `knopochnye-telefony-*`, `smartfony-android-*`, `smartfony-apple-iphoneios-*`, `smartfony-na-drugikh-os-*`, and `vosstanovlennye-smartfony-*` are intentionally skipped for bounded QA runs because they produced zero-result or off-target pages in live traffic.

## PDP flow

- PDP recognition uses `/product/...` path checks.
- `source_id` prefers `skuId`, then numeric path suffixes.
- PDPs now use plain HTTP by default; Playwright remains reserved for listing hydration and browser-only fallback cases.
- Uzum product URLs bounce through `id.uzum.uz` (`302 -> 303 -> same PDP URL`) before returning the final HTML. Store-local product requests therefore use `dont_filter=True` so Scrapy's redirect middleware can land back on the same PDP URL without being killed by the global dupefilter.
- The source of truth is JSON-LD first:
  - `ProductGroup.hasVariant[]` matching the current `skuId`
  - then direct `Product` JSON-LD
  - then HTML/meta fallbacks
- `ProductGroup` data is merged with the matching variant so the spider keeps variant price, availability, images, and `additionalProperty`, while still inheriting group-level description and shared images.
- Output stays minimal and is sent to the scraper persistence pipeline without typed normalization.
- Product URLs are only marked as seen after the request is actually admitted into the scheduler. If resource governance blocks a PDP on one listing page, the same PDP can still be retried later instead of being lost as a false duplicate.

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

- **Source discovery:** browser-rendered anchors plus serialized href fallback in raw HTML
- **Price:** JSON-LD `offers`, meta price tags, inline money text
- **Stock:** JSON-LD `availability`, then text fallback
- **Specs:** variant-aware JSON-LD `ProductGroup.hasVariant[].additionalProperty` first, then direct `Product.additionalProperty`, HTML `itemprop`, and tables
- **Images:** JSON-LD image arrays, `og:image`, `twitter:image`, image tags
- **Category hint:** URL/title heuristic classifier only
- **Source ID:** `skuId` in PDP URL is authoritative; JSON-LD `sku` is used to validate/match the current variant

## Known brittle points

- Uzum is heavily JS-driven, so listing coverage depends on Playwright timing and scroll behavior.
- Browser concurrency must stay conservative or the store becomes flaky.
- Some product details appear only in `ProductGroup` JSON-LD, not in visible DOM blocks.
- A few discovered subcategories still lead to weak or empty shells if Uzum changes live taxonomy faster than the allowlist.
- Uzum can still expose the same listing cards across several synthetic `page=` URLs; the spider now stops earlier on repeated shells, but live pagination drift remains a coverage risk.
- PDP timeout risk is lower now that product pages stay plain HTTP first, but browser fallback paths can still be slower than HTTP-first stores.
- Python 3.14 + `scrapy-playwright` can still emit teardown noise (`Task was destroyed but it is pending` / `Event loop is closed`) even when the crawl itself succeeds.

## Store-specific tuning still expected

- Playwright wait timings
- browser resource budgets
- lazy-loaded listing behavior
- occasional taxonomy drift in category URLs

## Intentionally left downstream

- typed characteristic normalization
- canonical product identity decisions
- CRM-side business payload shaping

## Acceptance / ops

- Fixture acceptance: `tests/acceptance/test_store_acceptance.py`
- Cross-store ingestion matrix: `tests/acceptance/test_store_ingestion_matrix.py`
- Bounded QA run:
  - `python -m scrapy crawl uzum -s CLOSESPIDER_ITEMCOUNT=3 -s CLOSESPIDER_PAGECOUNT=15 -L INFO`
- Acceptable bounded-run quality for Uzum:
  - products persist into scraper DB
  - `source_id`, `title`, `price_raw`, `image_urls`, `category_hint` are present
  - `raw_specs` should be non-empty on a meaningful subset once variant JSON-LD is available
- Live rollout should stay canary-first because browser stores are more sensitive than the HTTP-first references.
