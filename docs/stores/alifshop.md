# Store playbook: alifshop

## Summary

- **Spider:** `alifshop` in `infrastructure/spiders/alifshop.py`
- **Host:** `alifshop.uz`
- **Access mode:** HTTP-first
- **Reference basis:** old `E-katalog` Alifshop parser

Alifshop is now migrated onto the same raw-output contour as the other stores:

`listing -> PDP -> minimal structuring -> scraper DB -> outbox`

## Listing flow

- Seeds now focus on product-bearing electronics branches instead of catalog hubs that mostly fan out into empty intermediary pages:
  - `/ru/categories/smartfoni-apple`
  - `/ru/categories/smartfoni-samsung`
  - `/ru/categories/smartfoni-xiaomi`
  - `/ru/categories/smartfoni-honor`
  - `/ru/categories/smartfoni-tecno`
  - `/ru/categories/smartfoni-vivo`
  - `/ru/categories/smart-chasi`
  - `/ru/categories/fitnes-brasleti`
  - `/ru/categories/umnie-ochki`
  - `/ru/categories/umnie-koljca`
  - `/ru/categories/ekshen-kameri`
  - `/ru/categories/ochki-virtualjnoy-realjnosti`
- Listing discovery looks for `/ru|uz/moderated-offer/...` links in anchors and serialized HTML.
- Nested category discovery follows `/categories/...` links, but keeps traversal restricted to adjacent product-bearing tech branches such as phone brands, wearables, action cameras, and VR pages.
- Low-value accessory trees like cases, cables, chargers, straps, batteries, protective glass, and generic phone umbrellas are intentionally skipped, as are empty catalog hubs that do not expose PDPs directly.
- Pagination prefers a normal next link and falls back to synthetic `page=` increments.

## PDP flow

- PDP recognition is based on `/moderated-offer/...` paths.
- `source_id` comes from the numeric tail in the moderated-offer slug, with query-string fallback if available.
- Title, price, availability, description, images, and specs are extracted from lightweight meta tags and HTML rows.
- Output remains raw and minimally structured before it reaches the persistence layer.

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

- **Source discovery:** moderated-offer anchors and escaped href payloads
- **Price:** `product:price:amount`, then inline money text fallback
- **Stock:** `product:availability`, then body-text fallback
- **Specs:** bordered characteristics rows and body-text fallback after the characteristics header
- **Images:** `og:image`, `twitter:image`, Fortifai CDN links, `img` attrs
- **Category hint:** lightweight URL/title classifier

## Known brittle points

- Alifshop renders some specs with unstable utility-class combinations.
- Moderated-offer slugs can change formatting, so numeric-tail extraction must remain tolerant.
- Marketplace text can contain long promotional strings that need trimming without over-normalizing the product title.

## Store-specific tuning still expected

- CSS-class drift in the characteristics block
- occasional image source changes around Fortifai moderation URLs
- localized title boilerplate cleanup
- category allowlist refinement as the public catalog tree evolves

## Intentionally left downstream

- typed spec normalization
- canonical cross-store matching
- CRM/business payload enrichment

## Acceptance / ops

- Fixture acceptance: `tests/acceptance/test_store_acceptance.py`
- Cross-store ingestion matrix: `tests/acceptance/test_store_ingestion_matrix.py`
- Alifshop is the cleanest old-reference HTTP migration after MediaPark and a good template for stores that expose useful meta tags without needing a browser.
- Expanded bounded QA run:
  - `python -m scrapy crawl alifshop -s CLOSESPIDER_ITEMCOUNT=12 -s CLOSESPIDER_PAGECOUNT=20 -L INFO`
