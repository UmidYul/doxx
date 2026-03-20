# UZ Tech Scraper — AI Build Plan

Этот файл содержит готовые промты для поэтапной разработки проекта.
- **FOUNDATION** — отдать мощному агенту (Claude Opus, GPT-4o, Gemini Ultra) один раз
- **Итерации** — отдавать простому AI (Claude Sonnet, GPT-4o-mini) по одной

Перед каждым промтом — открывай `PROJECT.md` в контексте Cursor.

---

## FOUNDATION PROMPT
> Отдать мощному агенту. Он строит весь скелет проекта целиком.

```
You are a senior Python engineer. Build the complete project scaffold for a
Domain-Driven Design web scraper. Read PROJECT.md first — it is the source of
truth for every architectural decision.

Create the FULL directory tree with ALL files. Every file must be non-empty —
no "pass", no "TODO", no placeholder comments. Write real, working code.

=== WHAT TO BUILD ===

1. DOMAIN LAYER (domain/)
   - domain/category.py
     Category enum: PHONE, LAPTOP, TV, TABLET, APPLIANCE, UNKNOWN
     CategoryDetector class: detect(title: str, description: str) -> Category
     Uses keyword matching with flashtext. Keywords for each category in
     both Russian and Uzbek (e.g. телефон/smartfon/смартфон for PHONE).

   - domain/specs/base.py
     BaseSpecs(BaseModel):
       completeness_score: float = 0.0
       extraction_method: str = "unknown"
       raw_fields: dict = {}
       def compute_score(self) -> float  — ratio of non-None fields

   - domain/specs/phone.py — PhoneSpecs(BaseSpecs) with fields:
     display_size_inch, display_resolution, display_type, ram_gb,
     storage_gb, battery_mah, processor, processor_cores,
     main_camera_mp, front_camera_mp, os, sim_count, nfc, weight_g

   - domain/specs/laptop.py — LaptopSpecs(BaseSpecs) with fields:
     display_size_inch, display_resolution, processor, processor_cores,
     ram_gb, storage_gb, storage_type, gpu, os, battery_wh,
     weight_kg, usb_c_count, hdmi

   - domain/specs/tv.py — TVSpecs(BaseSpecs) with fields:
     display_size_inch, resolution, display_tech, smart_tv, os,
     hdmi_count, usb_count, refresh_rate_hz, has_wifi, has_bluetooth

   - domain/specs/appliance.py — ApplianceSpecs(BaseSpecs) with fields:
     power_w, volume_l, noise_db, energy_class, color, weight_kg,
     dimensions, warranty_months

   - domain/price.py
     Currency enum: UZS, USD
     PriceStatus enum: AVAILABLE, ON_REQUEST, OUT_OF_STOCK, DISCONTINUED
     Price(BaseModel): amount, currency, status, original_amount, discount_pct
     PriceRecord(BaseModel): price, scraped_at, source
     parse_price(raw: str) -> Price  — handles "1 500 000 сум", "по запросу",
     space-separated UZS thousands, comma decimal separator

   - domain/image.py
     ImageType enum: CLEAN_SHOT, MARKETING_BANNER, LIFESTYLE, ACCESSORIES, UNKNOWN
     ProductImage(BaseModel): url, local_path, image_type, score, is_processed,
     has_watermark, width, height, phash

   - domain/product.py
     SourceRecord(BaseModel): store, url, external_id, prices, last_scraped_at,
     is_available, is_bundle
     ProductVariant(BaseModel): id, family_id, color, storage_gb, ram_gb,
     region_variant, sources, images, specs, completeness_score, fingerprint
     ProductFamily(BaseModel): id, brand, model_name, category, canonical_specs

   - domain/events.py
     ProductDiscovered, PriceChanged, SpecsUpdated, ProductUnavailable
     All inherit from DomainEvent(BaseModel) with event_id, occurred_at

2. APPLICATION LAYER (application/)
   - application/deduplicator.py
     make_variant_fingerprint(brand, model, color, storage_gb, ram_gb) -> str
     Uses sha256 of normalized lowercased joined values.
     normalize_text(s) -> str: lowercase, strip, replace spaces with _

   - application/extractors/unit_normalizer.py
     normalize_storage(raw: str) -> Optional[int]  — handles TB→GB, "256 GB", "256GB"
     normalize_ram(raw: str) -> Optional[int]
     normalize_display(raw: str) -> Optional[float]  — handles comma decimal
     normalize_battery(raw: str) -> Optional[int]
     normalize_weight_g(raw: str) -> Optional[int]
     normalize_processor(raw: str, aliases: dict) -> str

   - application/extractors/patterns.py
     PHONE_PATTERNS: dict[str, list[str]]  — regex patterns per field, bilingual RU+UZ
     LAPTOP_PATTERNS: dict[str, list[str]]
     TV_PATTERNS: dict[str, list[str]]
     Patterns handle both Russian and Uzbek variants of each field.

   - application/extractors/regex_extractor.py
     RegexExtractor class:
       enrich(specs: BaseSpecs, text: str) -> BaseSpecs
       Uses flashtext for fast keyword scan, then re for value extraction.
       Never overwrites already-filled fields.
       Logs unmatched text to specs.raw_fields['_unmatched']

   - application/extractors/structured_extractor.py
     StructuredExtractor class:
       extract(raw: dict, schema_class: type[BaseSpecs]) -> BaseSpecs
       Maps raw dict keys to schema fields using FIELD_ALIASES dict.
       Runs unit normalizers on each extracted value.
       FIELD_ALIASES covers all Russian/Uzbek variations of field names
       (e.g. "Оперативная память", "RAM", "xotira" all -> ram_gb)

   - application/extractors/spec_extractor.py
     CATEGORY_SCHEMA_MAP: dict[Category, type[BaseSpecs]]
     SCORE_THRESHOLD_STRUCTURED = 0.7
     SCORE_THRESHOLD_REGEX = 0.4
     extract_specs(raw: dict, category: Category) -> BaseSpecs
     Cascade: structured → regex → mark as needs_llm=True if still low score.
     LLM step is NOT implemented here — just flag it.

3. INFRASTRUCTURE LAYER (infrastructure/)
   - infrastructure/spiders/base.py
     BaseProductSpider(scrapy.Spider):
       store_name: str = ""
       custom_settings with AUTOTHROTTLE, DOWNLOAD_DELAY=1.5
       parse() with zero-result guard and infinite pagination guard
       _is_duplicate_page() using set of seen page content hashes
       errback_default() logs error to Sentry and spider logger
       Abstract: parse_product_list(response) -> list[str]
       Abstract: parse_product_detail(response) -> dict
       Abstract: get_next_page(response) -> Optional[str]

   - infrastructure/pipelines/validate_pipeline.py
     ValidatePipeline: checks required fields (title, url, store),
     drops item and logs WARNING if missing. Never raises.

   - infrastructure/pipelines/dedup_pipeline.py
     DedupPipeline: computes fingerprint, checks Redis bloom filter,
     drops duplicate items, logs stats.

   - infrastructure/pipelines/persist_pipeline.py
     PersistPipeline: upserts ProductFamily, ProductVariant, SourceRecord,
     appends PriceRecord. Uses sync SQLAlchemy session (Scrapy is sync).

   - infrastructure/middlewares/ratelimit_middleware.py
     AdaptiveRateLimitMiddleware:
       Tracks response_time per domain (deque of last 10).
       If latest > 3x median: increase DOWNLOAD_DELAY by 1.5x (cap 30s).
       If response.status==200 and len(body)<500: raise IgnoreRequest.
       Log both cases with [RATE_LIMIT_SUSPECTED] and [EMPTY_BODY_200] tags.

   - infrastructure/middlewares/retry_middleware.py
     Extends Scrapy RetryMiddleware.
     Retries on: 429, 503, 520, 521, 522, connection timeout.
     Exponential backoff: 2^retry_count seconds, max 5 retries.

   - infrastructure/db/models.py
     SQLAlchemy ORM: ProductFamilyModel, ProductVariantModel, SourceRecordModel,
     PriceRecordModel, ProductImageModel, ScrapeJobModel.
     Exact schema from PROJECT.md. All tables, indexes, constraints.

4. CONFIG
   - config/settings.py
     Settings(BaseSettings) with all vars from .env.example.
     Single global instance: settings = Settings()

   - config/scrapy_settings.py
     Complete Scrapy settings file. Enables: AUTOTHROTTLE, rotating proxies,
     playwright handler, all custom middlewares and pipelines in correct order.

   - config/processor_aliases.json
     At least 30 real processor aliases covering:
     Snapdragon (SM85xx series), MediaTek Dimensity, Apple A-series,
     Exynos, Intel Core i-series model numbers -> marketing names.

5. DATABASE
   - infrastructure/db/migrations/env.py — Alembic env with async support
   - infrastructure/db/migrations/versions/001_initial.py
     Creates all tables from PROJECT.md schema exactly.

6. TASKS
   - tasks/celery_app.py
     Celery app + beat schedule for all 5 stores.
     mediapark/olx: daily 02:00, texnomart: daily 03:00,
     makro: daily 04:00, uzum: daily 05:00.
     Canary checks: every hour.

   - tasks/scrape_tasks.py
     run_spider(store_name: str) task with max_retries=3, exponential backoff.
     run_canary_checks() task.
     SPIDER_REGISTRY dict mapping store names to spider classes.

7. TESTS SCAFFOLD
   - tests/conftest.py — pytest fixtures: db session, redis mock, sample raw product
   - tests/canary/canary_products.py — CANARY_PRODUCTS dict with 2 real UZ store URLs

8. ROOT FILES
   - alembic.ini — points to infrastructure/db/migrations
   - scrapy.cfg — points to config.scrapy_settings
   - .gitignore — Python, venv, .env, data/, logs/, __pycache__

=== RULES ===
- Every file must have real working code. No stubs, no "pass", no TODO.
- Domain layer: zero imports from infrastructure or application.
- All Pydantic models use model_config = ConfigDict(arbitrary_types_allowed=True).
- Use from __future__ import annotations in all files.
- Price parsing must handle: "1 500 000", "1,500,000", "1500000", "по запросу",
  "по договорённости", "price on request", empty string.
- Regex patterns must have both Russian and Uzbek variants.
- processor_aliases.json must have real model numbers, not placeholders.
- Output every file completely. Do not truncate with "..." or "rest of file".
```

---

## РАЗДЕЛ 1 — Спайдеры

### Итерация 1.1 — Mediapark spider
```
Context: Read PROJECT.md and all files in infrastructure/spiders/ and
application/extractors/. Mediapark.uz is a static HTML store with a
structured spec table.

Task: Implement infrastructure/spiders/mediapark.py — a complete, working
Scrapy spider for mediapark.uz.

Requirements:
- Class MediaparkSpider(BaseProductSpider), store_name = "mediapark"
- start_category_urls covers: smartphones, laptops, TVs, tablets, appliances
  Use real mediapark.uz category URLs.
- parse_product_list(response): extract all product detail page URLs from
  a listing page. Handle pagination via get_next_page().
- parse_product_detail(response): extract:
    title, brand, model (parse from title if not separate field),
    price (current + original/crossed-out if present),
    all spec table rows into raw dict,
    all image URLs (full resolution, not thumbnails),
    availability status, external_id (product ID from URL or page)
- SPEC_FIELD_MAP: complete mapping of ALL Russian spec table labels on
  mediapark.uz to domain field names. Cover at least 25 fields.
- _unknown_fields handling: unmapped rows go to raw['_unknown_fields'],
  never dropped silently.
- Zero-result guard: if parse_product_list returns [] on page 1, log
  WARNING with [ZERO_RESULT] tag.
- Image extraction: get highest-resolution URLs, skip thumbnails.
  mediapark uses data-src for lazy images — handle both src and data-src.

Also update tests/canary/canary_products.py: add mediapark entry with a
real product URL (e.g. a Samsung smartphone) and assertions for brand,
at least 2 spec fields, and price range in UZS.

Output the complete file. No truncation.
```

### Итерация 1.2 — OLX spider
```
Context: Read PROJECT.md and infrastructure/spiders/base.py.
OLX Uzbekistan (olx.uz) is a classifieds marketplace — multiple sellers
post the same product. HTML is mostly static but listings vary wildly.

Task: Implement infrastructure/spiders/olx.py

Requirements:
- Class OlxSpider(BaseProductSpider), store_name = "olx"
- Categories: elektronika/telefony-i-aksessuary, noutbuki-i-kompyutery,
  televizory, planshety. Use real olx.uz URLs.
- parse_product_list: extract product URLs from search/category pages.
  OLX uses infinite scroll but also has page-based URLs (?page=N).
  Use page-based pagination.
- parse_product_detail:
    title: from h1
    price: from .price-label, handle "Договорная" -> PriceStatus.ON_REQUEST
    description: full text — this is the PRIMARY source for specs on OLX
    seller_type: "private" or "business" (affects trust of specs)
    images: extract from JSON-LD schema or og:image tags
    location: city (Tashkent, Samarkand, etc.) — store in raw
    posted_at: listing date
    external_id: from URL slug
- is_bundle detection: if title or description contains keywords like
  "комплект", "набор", "+ чехол", "в комплекте" -> set is_bundle=True
- Since OLX has no structured spec table, set raw['needs_regex_extraction']=True
  so the spec pipeline knows to use RegexExtractor heavily.

Add canary entry for OLX in canary_products.py.

Output the complete file.
```

### Итерация 1.3 — Texnomart spider
```
Context: Read PROJECT.md, infrastructure/spiders/base.py,
infrastructure/spiders/mediapark.py (as reference for structured spider).
Texnomart.uz uses a mix of server-rendered HTML and JS-loaded content.

Task: Implement infrastructure/spiders/texnomart.py

Requirements:
- Class TexnomartSpider(BaseProductSpider), store_name = "texnomart"
- use_playwright = True in custom_settings (some pages need JS)
- custom_settings: PLAYWRIGHT_BROWSER_TYPE = "chromium",
  PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000
- Requests use meta={"playwright": True} only for product detail pages,
  NOT for listing pages (save resources).
- parse_product_list: works with regular HTTP (no playwright needed).
- parse_product_detail: 
    Wait for selector: "table.product-characteristics" or equivalent.
    Extract spec table (label/value rows).
    Extract price including installment price if shown separately.
    Extract all product images including zoom/fullsize URLs.
    Extract "Нет в наличии" status -> PriceStatus.OUT_OF_STOCK
- SPEC_FIELD_MAP: cover texnomart's specific field names (they differ
  from mediapark — use Uzbek labels too).
- Handle session: texnomart may require accepting cookie consent popup.
  Use Playwright to click it if present before extracting data.

Add canary entry. Output complete file.
```

### Итерация 1.4 — Makro spider
```
Context: Read PROJECT.md, infrastructure/spiders/base.py.
Makro.uz exposes a REST JSON API — no HTML parsing needed.

Task: Implement infrastructure/spiders/makro.py

Requirements:
- Class MakroSpider(BaseProductSpider), store_name = "makro"
- API-based: use Scrapy's JsonRequest or Request with JSON response parsing.
- Research and use the real makro.uz API endpoints:
    List: GET /api/catalog/products?categoryId=X&page=N&limit=48
    Detail: GET /api/products/{slug} or /api/catalog/products/{id}
  If exact endpoints differ, use the closest working alternative.
- parse_product_list: extract product IDs/slugs from API response,
  yield detail API requests.
- parse_product_detail: extract from JSON response:
    All fields available in the API response.
    Map API field names to domain model fields.
    specs come as a structured array [{name, value}] in the API.
- Cursor-based pagination: if API uses cursor/offset, implement correctly.
- Rate limiting: Makro API may return 429. Handle via retry middleware.
  Add specific 429 handling: extract Retry-After header if present.

Add canary entry. Output complete file.
```

### Итерация 1.5 — Uzum spider (GraphQL)
```
Context: Read PROJECT.md fully. Read ALL existing spiders in
infrastructure/spiders/. Uzum.uz is a React SPA using GraphQL.
This is the most complex spider.

Task: Implement infrastructure/spiders/uzum.py AND
infrastructure/middlewares/uzum_graphql_middleware.py

The approach: instead of parsing the React DOM (unreliable), intercept
GraphQL network responses using Playwright's page.on('response').

Requirements for uzum_graphql_middleware.py:
- PlaywrightContextManager that intercepts responses matching:
  URL contains "/api/storefront" and Content-Type is application/json
- Stores intercepted JSON payloads in response.meta['graphql_payloads']
  as a list (multiple GraphQL calls per page load).
- Handles cases where payload is empty or malformed (try/except).

Requirements for uzum.py:
- Class UzumSpider(BaseProductSpider), store_name = "uzum"
- use_playwright = True, uses the graphql middleware
- For listing pages: scroll to bottom to trigger lazy loading of all
  products before extracting links. Use Playwright evaluate:
  await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
  then wait 1 second, repeat 3 times.
- parse_product_detail:
    Try to extract from intercepted GraphQL payloads first.
    GraphQL payload structure: data.makeSearch.items[].catalogItem
    or data.getProductInfo depending on query type.
    Fall back to DOM parsing if GraphQL payload not available.
    Description field is the main spec source (unstructured text).
    Extract all image URLs from payload or from DOM img tags.
    Set raw['needs_llm_extraction'] = True if completeness_score < 0.4
    after regex extraction (Uzum descriptions are often incomplete).
- Handle Uzum-specific: products can have variants shown as color swatches.
  Each swatch is a separate URL. Mark current variant's color from
  active/selected swatch.
- Region variant detection: if title or description contains "Global",
  "EU version", "Snapdragon version" etc. -> set region_variant field.

Add canary entry. Output both files completely.
```

---

## РАЗДЕЛ 2 — Extraction Pipeline

### Итерация 2.1 — Regex patterns (bilingual)
```
Context: Read PROJECT.md and application/extractors/patterns.py.

Task: Rewrite application/extractors/patterns.py with COMPLETE, production-
ready regex patterns for ALL product categories. This file is critical —
bad patterns = bad data.

Requirements:

PHONE_PATTERNS dict covering fields:
  ram_gb, storage_gb, display_size_inch, display_resolution, display_type,
  battery_mah, processor, main_camera_mp, front_camera_mp, os,
  sim_count, nfc, weight_g

LAPTOP_PATTERNS dict covering fields:
  ram_gb, storage_gb, storage_type, display_size_inch, display_resolution,
  processor, gpu, os, battery_wh, weight_kg, usb_c_count, hdmi

TV_PATTERNS dict covering fields:
  display_size_inch, resolution, display_tech, refresh_rate_hz,
  hdmi_count, usb_count, has_wifi, has_bluetooth, smart_tv, os

For each field provide AT LEAST 4 patterns covering:
  1. Russian full text: "Оперативная память: 8 ГБ"
  2. Russian short: "8 ГБ RAM" / "8GB ОЗУ"
  3. Uzbek: "8 GB RAM" / "8 GB xotira"
  4. Technical notation: "8GB" / "8 GB" with no label

Rules for patterns:
- Use named groups where helpful: (?P<value>\d+)
- Handle both . and , as decimal separator for float values
- Handle both Latin and Cyrillic GB/ГБ variants
- Patterns for nfc/wifi/bluetooth: detect presence by keyword, return True
- OS patterns: detect "Android 14", "iOS 17", "Windows 11", "MIUI 14" etc.
- storage_type: detect "SSD", "NVMe", "HDD", "eMMC"
- Add UNIT_CONVERSION dict: TB->GB multiplier, etc.
- Add BOOLEAN_FIELDS set: fields that return True/False not numeric values

Also add compile_patterns() function that pre-compiles all patterns with
re.IGNORECASE | re.UNICODE for performance.

Write a comprehensive docstring for each pattern group explaining
what edge cases it handles. Output the complete file.
```

### Итерация 2.2 — Structured extractor + FIELD_ALIASES
```
Context: Read PROJECT.md, application/extractors/structured_extractor.py,
application/extractors/unit_normalizer.py, domain/specs/*.py.

Task: Rewrite application/extractors/structured_extractor.py with a
complete FIELD_ALIASES mapping and robust extraction logic.

Requirements:

FIELD_ALIASES: a dict mapping every known Russian/Uzbek spec table label
to the corresponding domain field name. Must cover ALL labels from:
- mediapark.uz spec tables (Russian)
- texnomart.uz spec tables (Russian + Uzbek)
- makro.uz API field names (English + Russian)
- common variations sellers use on OLX

Minimum 80 alias entries. Examples:
  "Оперативная память" -> "ram_gb"
  "RAM" -> "ram_gb"
  "Xotira" -> "storage_gb"  (Uzbek for memory)
  "Ichki xotira" -> "storage_gb"  (Uzbek for internal storage)
  "Batareya sig'imi" -> "battery_mah"  (Uzbek for battery capacity)
  "Ekran o'lchami" -> "display_size_inch"  (Uzbek for screen size)
  ... (cover all phone, laptop, TV fields)

StructuredExtractor class:
  extract(raw: dict, schema_class: type[BaseSpecs]) -> BaseSpecs
  
  For each key in raw:
    1. Normalize key: lowercase, strip, remove extra spaces/colons
    2. Look up in FIELD_ALIASES
    3. If found: run appropriate unit_normalizer for that field
    4. Handle type mismatch: if ram_gb value > 32 (GB), it's likely
       storage — swap with warning log [SPEC_SANITY_SWAP]
    5. Unknown keys -> raw_fields['_unknown_fields'][key] = value
  
  After extraction: call specs.compute_score() and assign.

Also add fuzzy_match(label: str, threshold: float = 0.8) -> Optional[str]
using difflib.SequenceMatcher as fallback for labels not in FIELD_ALIASES.
Log fuzzy matches with [FUZZY_MATCH] tag for monitoring.

Output the complete file.
```

### Итерация 2.3 — LLM extractor
```
Context: Read PROJECT.md, domain/specs/*.py, application/extractors/
spec_extractor.py, config/settings.py.

Task: Implement application/extractors/llm_extractor.py

This extractor is the LAST resort — only called when structured + regex
extraction yields completeness_score < 0.4. It must be:
- Cost-efficient: cache results aggressively
- Reliable: validate LLM output strictly with Pydantic
- Transparent: log every LLM call with cost estimate

Requirements:

LLMExtractor class:
  __init__(self, cache_backend: Redis)
  
  enrich(specs: BaseSpecs, text: str, schema_class: type[BaseSpecs]) -> BaseSpecs
    1. Check cache: key = sha256(schema_class.__name__ + text[:500])
       If hit: return cached specs, log [LLM_CACHE_HIT]
    2. If settings.LLM_EXTRACTION_ENABLED is False: return specs as-is
    3. Build prompt (see below)
    4. Call Anthropic claude-haiku-3 (cheapest, fast enough for extraction)
       max_tokens=512, temperature=0
    5. Parse JSON response with Pydantic, fill only None fields in specs
       (never overwrite already-extracted values)
    6. Cache result with TTL = settings.LLM_CACHE_TTL_DAYS * 86400
    7. Log: [LLM_EXTRACTION] store=X category=Y tokens=Z cached=False

PROMPT template:
  System: "You are a product spec extractor. Extract technical specifications
  from product descriptions. Return ONLY valid JSON. No explanation."
  
  User: "Category: {category}
  Text (Russian or Uzbek): {text}
  
  Extract these fields (null if not found):
  {schema_fields_with_types}
  
  Rules:
  - ram_gb and storage_gb must be integers (GB)
  - display_size_inch must be float (inches, convert cm if needed)
  - battery_mah must be integer
  - nfc/wifi/bluetooth: true/false only
  - processor: marketing name only (e.g. 'Snapdragon 8 Gen 2', not 'SM8550')
  - Return ONLY JSON, no markdown, no explanation"

Error handling:
  - JSONDecodeError -> log [LLM_JSON_PARSE_ERROR], return original specs
  - Pydantic ValidationError -> log [LLM_VALIDATION_ERROR], return original
  - API error -> log [LLM_API_ERROR], return original (never raise)
  - Rate limit -> wait 5s, retry once, then return original

Also implement estimate_cost(text: str) -> float returning USD cost estimate
based on token count (haiku pricing: $0.25/1M input tokens).

Output the complete file.
```

### Итерация 2.4 — Image pipeline
```
Context: Read PROJECT.md sections on image pipeline. Read
infrastructure/pipelines/ directory and domain/image.py.

Task: Implement infrastructure/pipelines/image_pipeline.py — a complete
image processing pipeline that downloads, classifies, deduplicates,
optionally removes backgrounds, scores, and stores product images.

Requirements:

ImageClassifier class (singleton, initialized once):
  Uses open_clip ViT-B-32 model.
  LABELS list with 4 categories (from PROJECT.md).
  classify(image_path: str) -> tuple[ImageType, float]
  Handles exceptions: if classification fails, return UNKNOWN, 0.0

BackgroundRemover class:
  remove(image_path: str) -> tuple[str, float]
    Calls rembg.remove(), saves to image_path.stem + "_nobg.png"
    Returns (new_path, confidence_score)
    confidence estimated from: ratio of non-transparent pixels in alpha channel
    If rembg throws any exception: return (original_path, 0.0)

score_image(metadata: dict) -> float  — exact scoring from PROJECT.md

ProductImagePipeline(ImagesPipeline):
  Extends Scrapy's built-in ImagesPipeline for downloading.
  
  get_media_requests(item, info):
    Yield requests for all image URLs in item['image_urls']
    Skip URLs matching PLACEHOLDER_PHASHES patterns
  
  item_completed(results, item, info):
    For each successfully downloaded image:
      1. Compute phash — skip if already seen (within this product)
      2. Classify with CLIP
      3. If classified as MARKETING_BANNER or LIFESTYLE:
           Try rembg background removal
           If confidence > settings.REMBG_CONFIDENCE_THRESHOLD: use result
           Else: use original
      4. Score image
      5. Build ProductImage domain object
    
    Sort by score descending.
    Keep top settings.MAX_IMAGES_PER_PRODUCT images.
    Assign to item['images']
    
  PLACEHOLDER_PHASHES: set of known placeholder image hashes
  (gray squares, "no image" placeholders common on UZ sites)

Also implement detect_lazy_images(response) utility function:
  Finds img tags where src is empty/data-URI but data-src has real URL.
  Returns list of real image URLs.
  Handles: data-src, data-lazy-src, data-original attributes.

Output the complete file.
```

---

## РАЗДЕЛ 3 — База данных

### Итерация 3.1 — ORM models + repository
```
Context: Read PROJECT.md section "Database Schema" completely.
Read domain/product.py, domain/price.py, domain/image.py.

Task: Implement infrastructure/db/models.py AND
infrastructure/repositories/product_repo.py

Requirements for models.py:
  All SQLAlchemy 2.0 ORM models matching PROJECT.md schema EXACTLY:
  - ProductFamilyModel
  - ProductVariantModel (specs as JSONB, images as relationship)
  - SourceRecordModel
  - PriceRecordModel (append-only — no update methods)
  - ProductImageModel
  - ScrapeJobModel
  
  All indexes from PROJECT.md.
  Proper relationships with lazy="select".
  __repr__ methods on all models.
  to_domain() method on each model returning the corresponding
  domain object (ProductFamily, ProductVariant, etc.)
  
  Base = declarative_base() with naming convention for constraints.

Requirements for product_repo.py:
  ProductRepository class using SQLAlchemy sync session (Scrapy is sync):
  
  upsert_family(family: ProductFamily) -> ProductFamilyModel
    INSERT ... ON CONFLICT (brand, model_name, category) DO UPDATE
    Update canonical_specs only if new completeness_score is higher.
  
  upsert_variant(variant: ProductVariant) -> ProductVariantModel
    INSERT ... ON CONFLICT (fingerprint) DO UPDATE
    Update specs, completeness_score, updated_at.
    Never overwrite sources list — merge it.
  
  upsert_source(source: SourceRecord, variant_id: UUID) -> SourceRecordModel
    INSERT ... ON CONFLICT (store, url) DO UPDATE is_available, last_scraped_at
  
  append_price(price: PriceRecord, source_id: UUID) -> PriceRecordModel
    Always INSERT, never UPDATE. Append-only.
    Skip if same amount + status recorded in last 6 hours (dedup).
  
  get_variant_by_fingerprint(fingerprint: str) -> Optional[ProductVariant]
  
  get_latest_price(source_id: UUID) -> Optional[Price]
  
  All methods: wrap in try/except, log errors, never raise to caller.

Output both files completely.
```

### Итерация 3.2 — Alembic migration
```
Context: Read infrastructure/db/models.py completely.
Read alembic.ini and infrastructure/db/migrations/env.py.

Task: Create the initial Alembic migration that builds the complete
database schema from scratch.

File: infrastructure/db/migrations/versions/001_initial_schema.py

Requirements:
- Uses op.create_table() for every table in exact order respecting FKs:
  1. product_families
  2. product_variants
  3. source_records
  4. price_records
  5. product_images
  6. scrape_jobs

- Every column exactly matches models.py and PROJECT.md schema.
- All indexes: op.create_index() for every index listed in PROJECT.md.
- Primary keys use gen_random_uuid() server default.
- price_records has NO update trigger — it is append-only by convention
  (enforced at application layer, not DB constraint).
- specs column: JSONB with default '{}'.
- Downgrade: drops all tables in reverse FK order.
- Add a comment at top: "# Generated manually — do not auto-generate"
  because we control this schema precisely.

Also update infrastructure/db/migrations/env.py:
- target_metadata = Base.metadata
- Use synchronous connection (Alembic doesn't need async).
- DATABASE_URL_SYNC from settings (postgresql:// not postgresql+asyncpg://).

Output both files completely.
```

---

## РАЗДЕЛ 4 — Anti-detection & Reliability

### Итерация 4.1 — Middlewares
```
Context: Read PROJECT.md sections "Anti-Detection & Network" and
"Edge Cases & Solutions" (Network level). Read config/scrapy_settings.py.

Task: Implement ALL remaining middlewares completely.

1. infrastructure/middlewares/stealth_middleware.py
   PlaywrightStealthMiddleware:
   - Runs playwright_stealth.stealth_async(page) on every new Playwright page
   - Injects realistic viewport: 1920x1080
   - Injects navigator.webdriver = undefined override
   - Randomizes: window.screen dimensions (±5%), timezone (Asia/Tashkent),
     language (ru-RU,ru;q=0.9,uz;q=0.8)
   - process_request: if "playwright" in request.meta, apply stealth

2. infrastructure/middlewares/mobile_redirect_middleware.py
   MobileRedirectMiddleware:
   - process_response: if response.url contains "m." and request.url did not:
     Force retry with desktop User-Agent and dont_filter=True
   - Detect mobile redirect patterns: m.site.uz, mobile.site.uz, site.uz/m/
   - Max 1 retry per request to avoid loop

3. infrastructure/middlewares/session_middleware.py
   SessionMiddleware:
   - Maintains per-domain session cookies in Redis
   - process_request: attach stored cookies to request headers
   - process_response: if 401/403: clear session, try to re-authenticate
     (spider must implement authenticate() method if needed)
   - Cookie expiry: store scraped_at timestamp, refresh if > 2 hours old

4. Update infrastructure/middlewares/retry_middleware.py:
   Add handling for soft blocks:
   - response.status in [429, 503]: exponential backoff 2^n seconds
   - response.status == 200 but contains block keywords:
     "Access Denied", "Captcha", "blocked", "robot" in body
     -> treat as block, delay 30s, retry
   - Extract and respect Retry-After header when present

5. Update config/scrapy_settings.py:
   Add all new middlewares in correct priority order.
   Add PLAYWRIGHT settings for stealth.
   Document each middleware's priority number with a comment.

Output all files completely.
```

### Итерация 4.2 — Canary system
```
Context: Read PROJECT.md section "Observability & Alerting".
Read tasks/scrape_tasks.py and all existing spider files.

Task: Build the complete canary assertion system.

1. tests/canary/canary_products.py
   Complete CANARY_PRODUCTS dict for all 5 stores.
   Each entry must have:
   - url: real product URL on that store (use a popular Samsung or iPhone)
   - store: store name
   - assertions: dict of field_path -> expected value or callable
   - Fields to assert: brand, at least 2 spec fields, price range in UZS
   
   Example format:
   "mediapark": {
     "url": "https://mediapark.uz/products/...",
     "store": "mediapark",
     "assertions": {
       "brand": "Samsung",
       "specs.ram_gb": 8,
       "specs.storage_gb": lambda v: v in [128, 256],
       "price.amount": lambda v: v is not None and 5_000_000 < v < 25_000_000,
       "images": lambda imgs: len(imgs) >= 1,
     }
   }

2. tasks/canary_tasks.py
   run_canary_checks() Celery task:
   
   For each store in CANARY_PRODUCTS:
     - Scrape the canary URL using run_spider_single_url(url, store)
     - For each assertion in config:
         actual = deep_get(result, field_path)  (supports dot notation)
         expected = assertion
         ok = expected(actual) if callable(expected) else actual == expected
         if not ok: log [CANARY_FAIL] store=X field=Y expected=Z got=W
     - Report: canary_results dict with pass/fail per store
     - If any failure: send alert via log_canary_alert(store, failures)
   
   log_canary_alert(store: str, failures: list):
     - Always: log ERROR with full details
     - If SENTRY_DSN set: capture_message to Sentry with tag canary=True
     - Future: webhook support via settings.CANARY_WEBHOOK_URL
   
   run_spider_single_url(url: str, store: str) -> dict:
     Runs the appropriate spider on a single URL and returns the
     parsed item as a dict. Uses CrawlerRunner, not CrawlerProcess
     (CrawlerRunner is non-blocking, works in async context).

3. Update tasks/celery_app.py:
   Import canary tasks. Add hourly beat schedule.
   Add CELERY_TASK_ROUTES to route canary tasks to dedicated queue.

Output all files completely.
```

---

## РАЗДЕЛ 5 — Финализация

### Итерация 5.1 — Deduplication (variants + families)
```
Context: Read PROJECT.md sections on deduplication edge cases.
Read domain/product.py, application/deduplicator.py,
infrastructure/pipelines/dedup_pipeline.py.

Task: Implement robust deduplication at two levels.

1. Rewrite application/deduplicator.py completely:

   normalize_text(s: Optional[str]) -> str:
     lowercase, strip, remove extra whitespace, transliterate
     common UZ/RU brand name variants to canonical:
     "самсунг" -> "samsung", "эпл" -> "apple", "сяоми" -> "xiaomi"
   
   extract_brand(title: str) -> Optional[str]:
     Detect brand from title using KNOWN_BRANDS list (50+ brands).
     KNOWN_BRANDS covers all major tech brands sold in Uzbekistan.
   
   extract_model(title: str, brand: str) -> Optional[str]:
     Remove brand name from title, remove color/storage indicators,
     return clean model name. E.g.:
     "Samsung Galaxy A54 256GB Черный" -> "Galaxy A54"
   
   detect_variant_attributes(title: str, description: str) -> dict:
     Returns: {color, storage_gb, ram_gb, region_variant}
     Color: detect from title/description using COLOR_KEYWORDS dict
       (Russian + Uzbek color names -> canonical English name)
     Storage: extract number before GB/ГБ that's > 32 (likely storage)
     RAM: extract number before GB that's <= 32 (likely RAM)
     Region: detect "Global", "EU", "RU", "KZ", "CN" versions
   
   make_family_fingerprint(brand: str, model: str, category: Category) -> str
   make_variant_fingerprint(brand, model, color, storage_gb, ram_gb) -> str
   
   is_bundle(title: str, description: str) -> bool:
     Check for bundle keywords in RU + UZ languages.
     BUNDLE_KEYWORDS list of 20+ patterns.

2. Rewrite infrastructure/pipelines/dedup_pipeline.py:

   DedupPipeline:
     Uses Redis bloom filter (via scrapy-redis BloomFilter) for fast
     URL-level dedup to skip already-scraped pages.
     
     Uses fingerprint + PostgreSQL upsert for product-level dedup.
     
     process_item(item, spider):
       1. Extract brand (from item or from title via extract_brand)
       2. Extract model (via extract_model)  
       3. Detect variant attributes
       4. Compute family + variant fingerprints
       5. Enrich item with: brand, model_name, fingerprint,
          variant_color, variant_storage_gb, variant_ram_gb,
          is_bundle, region_variant
       6. Check bloom filter for URL — if seen: DropItem with stat increment
       7. Add URL to bloom filter
       Return enriched item (never drop based on fingerprint here —
       persist_pipeline handles upsert logic)

Output both files completely.
```

### Итерация 5.2 — Full integration test
```
Context: Read ALL files in the project. This is a final integration check.

Task: Write integration tests that verify the complete pipeline works
end-to-end, using mock HTTP responses (no real network calls).

File: tests/integration/test_pipeline_e2e.py

Tests to implement:

1. test_mediapark_phone_full_pipeline:
   - Mock HTTP response with realistic mediapark.uz product HTML
     (Samsung Galaxy phone with full spec table)
   - Run through: spider.parse_product_detail -> ValidatePipeline ->
     SpecExtractorPipeline -> DedupPipeline (mock Redis) -> 
     PersistPipeline (SQLite in-memory)
   - Assert: ProductVariant created with PhoneSpecs, completeness_score > 0.7,
     price parsed correctly, fingerprint computed, SourceRecord created

2. test_olx_laptop_regex_extraction:
   - Mock OLX listing with laptop description in Russian
     (description-only, no spec table)
   - Assert: LaptopSpecs extracted via regex, key fields filled,
     needs_llm_extraction = False (regex was sufficient)

3. test_uzum_price_parsing:
   - Test parse_price() with inputs:
     "1 500 000 сум" -> Price(amount=1500000, currency=UZS)
     "750 000" -> Price(amount=750000, currency=UZS)
     "По договорённости" -> Price(status=ON_REQUEST)
     "0" -> Price(status=ON_REQUEST)  (zero price = not set)
     "" -> Price(status=ON_REQUEST)

4. test_variant_deduplication:
   - Create two items with same phone, different sources (mediapark + olx)
   - Run both through DedupPipeline + PersistPipeline
   - Assert: 1 ProductFamily, 1 ProductVariant, 2 SourceRecords

5. test_canary_assertion_format:
   - Verify all entries in CANARY_PRODUCTS have required keys
   - Verify all assertions are either a scalar or callable

6. test_image_scoring:
   - Create mock ProductImage objects with different types and metadata
   - Assert scoring produces correct ranking (CLEAN_SHOT ranks highest)

Use pytest-scrapy for spider tests. Use SQLite :memory: for DB tests.
Use fakeredis for Redis mock.

Include conftest.py fixtures for: db_session, mock_redis, sample_raw_phone,
sample_raw_laptop.

Output the complete test file and updated conftest.py.
```

### Итерация 5.3 — README + Makefile
```
Context: Read PROJECT.md and all project files.

Task: Create two developer-facing files.

1. README.md — complete developer documentation:
   
   Sections:
   - Quick Start (5 commands from zero to running)
   - Architecture overview (text description of DDD layers)
   - Adding a new store (step-by-step with checklist)
   - Configuration reference (all .env variables with examples)
   - Running spiders (scrapy crawl commands with useful -s flags)
   - Monitoring (how to check canary status, Adminer URL, Redis CLI)
   - Common issues & fixes:
       "Spider returns 0 items" -> check ZERO_RESULT logs
       "Specs completeness low" -> check _unknown_fields in DB
       "Docker won't start" -> common Docker Desktop issues on Windows
       "Poetry not found" -> PATH issue, how to fix on Windows
   
   Keep it practical. No marketing language. Every command must be real
   and runnable.

2. Makefile — shortcuts for common dev tasks:
   
   make up          -> docker compose up -d postgres redis
   make down        -> docker compose down
   make migrate     -> poetry run alembic upgrade head
   make rollback    -> poetry run alembic downgrade -1
   make shell       -> poetry run python -c "from config.settings import settings; print(settings)"
   make crawl store=mediapark -> poetry run scrapy crawl $(store) -s CLOSESPIDER_ITEMCOUNT=10
   make crawl-all   -> run all 5 spiders sequentially with limit 50
   make canary      -> poetry run celery -A tasks.celery_app call tasks.canary_tasks.run_canary_checks
   make worker      -> poetry run celery -A tasks.celery_app worker --loglevel=info
   make test        -> poetry run pytest tests/ -v
   make test-unit   -> poetry run pytest tests/unit/ -v
   make test-canary -> poetry run pytest tests/canary/ -v
   make lint        -> poetry run ruff check . && poetry run black --check .
   make format      -> poetry run black . && poetry run ruff check --fix .
   make logs store=mediapark -> docker compose logs -f uz_scraper_worker | grep $(store)
   make db-shell    -> docker compose exec postgres psql -U scraper -d uz_scraper
   make redis-cli   -> docker compose exec redis redis-cli

   Add .PHONY for all targets. Add help target that prints all commands.

Output both files completely.
```
