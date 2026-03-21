# UZ Tech Scraper — AI Build Plan

Готовые промты для поэтапной разработки.
- **FOUNDATION** — мощному агенту (Opus, GPT-4o) один раз
- **Итерации** — простому AI по одной, всегда с PROJECT.md в контексте

---

## FOUNDATION PROMPT
> Строит весь скелет проекта. Отдать один раз мощному агенту.

```
You are a senior Python engineer. Build the complete project scaffold.
Read PROJECT.md first — it is the single source of truth.

The scraper is a SENSOR service. It scrapes, normalizes, and sends
ONLY deltas to CRM via REST API. It never touches CRM's database.
It has its own lightweight database: per-store tables + parse_cache.

Create ALL files listed in the project structure. Every file must have
real working code — no stubs, no pass, no TODO.

=== WHAT TO BUILD ===

1. DOMAIN (domain/)

   domain/events.py
     Pydantic models for all CRM API events:
     - ProductFoundEvent: event, source, source_url, source_id,
       crm_product_id (Optional), product: ProductPayload,
       listing: ListingPayload
     - PriceChangedEvent: event, crm_listing_id, listing: ListingPayload
     - OutOfStockEvent: event, crm_listing_id, parsed_at
     - CharacteristicAddedEvent: event, crm_product_id, characteristics: dict
     - CRMSyncResponse: status, crm_listing_id, crm_product_id, action
     - ProductPayload: name, brand, characteristics: dict
     - ListingPayload: price (Decimal), currency, in_stock, parsed_at

   domain/raw_product.py
     RawProduct(BaseModel): all fields a spider can return.
     source, url, source_id, title, price_str, in_stock,
     raw_specs: dict, image_urls: list[str], description,
     raw_html: Optional[str]

   domain/normalized_product.py
     NormalizedProduct(BaseModel): cleaned version ready for CRM.
     source, url, source_id, brand, name, price: Decimal,
     currency, in_stock, specs: BaseSpecs, images: list[str],
     extraction_method: str, completeness_score: float

   domain/specs/base.py
     BaseSpecs with completeness_score, extraction_method, raw_fields.
     compute_score() → ratio of non-None fields.

   domain/specs/phone.py — PhoneSpecs(BaseSpecs):
     display_size_inch, display_resolution, display_type, ram_gb,
     storage_gb, battery_mah, processor, main_camera_mp,
     front_camera_mp, os, sim_count, nfc, weight_g

   domain/specs/laptop.py — LaptopSpecs(BaseSpecs):
     display_size_inch, processor, ram_gb, storage_gb, storage_type,
     gpu, os, battery_wh, weight_kg, hdmi, usb_c_count

   domain/specs/tv.py — TVSpecs(BaseSpecs):
     display_size_inch, resolution, display_tech, smart_tv, os,
     hdmi_count, refresh_rate_hz, has_wifi, has_bluetooth

   domain/specs/appliance.py — ApplianceSpecs(BaseSpecs):
     power_w, volume_l, energy_class, color, weight_kg, warranty_months

2. APPLICATION (application/)

   application/crm_client.py
     Async httpx client. Methods:
     - sync_event(event) → CRMSyncResponse
     - sync_batch(events: list) → list[CRMSyncResponse]
     - find_in_catalog(source, source_id) → Optional[CRMSyncResponse]
     Auth header: X-Parser-Key from settings.
     Timeout: 10s. On connection error: raise CRMUnavailableError.

   application/event_sender.py
     send_event(event) → bool:
       Try crm_client.sync_event().
       On CRMUnavailableError: save to pending_events, return False.
       On success: return True.
     send_batch(events) → int (sent count):
       Split into chunks of 100.
       On partial failure: save failed ones to pending_events.

   application/delta_detector.py
     DeltaDetector:
       detect(normalized: NormalizedProduct, cache: ParseCache | None)
         → list[BaseEvent]
       If cache is None: return [ProductFoundEvent(...)]
       If price changed: return [PriceChangedEvent(...)]
       If in_stock changed False: return [OutOfStockEvent(...)]
       If new spec fields found: return [CharacteristicAddedEvent(...)]
       If nothing changed: return [] ← this is the core optimization

   application/parse_orchestrator.py
     ParseOrchestrator:
       fast_parse(source_name: str): price + in_stock only, no full page
       full_parse(source_name: str): complete card with specs and images
       discover(source_name: str): find new URLs, add to parse_queue
     Each method: logs to parse_logs, handles errors per spec.

   application/extractors/unit_normalizer.py
     normalize_price(raw: str) → Decimal | None
       Handle: "2 990 000", "2,990,000", "2990000", space-separated UZS
       Return None for: "По договорённости", "по запросу", "0", ""
     normalize_storage(raw: str) → int | None  (GB)
     normalize_ram(raw: str) → int | None  (GB)
     normalize_display(raw: str) → float | None  (inches, handle comma)
     normalize_battery(raw: str) → int | None  (mAh)
     normalize_weight_g(raw: str) → int | None
     normalize_brand(raw: str, aliases: dict) → str
       aliases: "эпл"→"Apple", "самсунг"→"Samsung", "сяоми"→"Xiaomi" etc.
     normalize_processor(raw: str, aliases: dict) → str
       aliases from config/processor_aliases.json

   application/extractors/patterns.py
     PHONE_PATTERNS, LAPTOP_PATTERNS, TV_PATTERNS
     Each: dict[field_name, list[regex_pattern]]
     Bilingual RU + UZ. At least 4 patterns per field.

   application/extractors/structured_extractor.py
     FIELD_ALIASES: 80+ entries mapping RU/UZ table labels → field names
     StructuredExtractor.extract(raw_specs: dict, schema) → BaseSpecs
     Fuzzy match fallback via difflib for unknown labels.

   application/extractors/regex_extractor.py
     RegexExtractor.enrich(specs: BaseSpecs, text: str) → BaseSpecs
     Uses flashtext for fast scan, re for value extraction.
     Never overwrites already-filled fields.

   application/extractors/llm_extractor.py
     LLMExtractor.enrich(specs, text, schema) → BaseSpecs
     Uses claude-haiku-3, max_tokens=512, temperature=0.
     Cache by sha256(schema_name + text[:500]) in Redis.
     TTL = LLM_CACHE_TTL_DAYS * 86400.
     On any error: return original specs unchanged.

   application/extractors/spec_extractor.py
     extract_specs(raw_specs: dict, description: str, category) → BaseSpecs
     Cascade: structured (≥0.7) → regex (≥0.4) → llm

3. INFRASTRUCTURE (infrastructure/)

   infrastructure/spiders/base.py
     BaseProductSpider(scrapy.Spider):
       Abstract: fast_parse_item(response) → dict
       Abstract: full_parse_item(response) → dict
       Abstract: discover_urls(response) → list[str]
       _zero_result_guard(urls, response)
       _is_duplicate_page(response) → bool  (bloom filter)
       errback_default(failure)  (log + Sentry)

   infrastructure/pipelines/validate_pipeline.py
     Check title and url present. Drop with WARNING if missing.

   infrastructure/pipelines/normalize_pipeline.py
     RawProduct → NormalizedProduct.
     Detect category, extract specs cascade, normalize price.

   infrastructure/pipelines/image_pipeline.py
     ImageClassifierPipeline: download bytes to memory only (no disk, no Storage),
     CLIP classify, rembg in memory if banner-like, phash dedupe.
     Output: item["image_urls_ranked"] = best-first list of original store URLs
     (same strings as on the shop; CRM downloads/stores images itself).

   infrastructure/pipelines/delta_pipeline.py
     Upsert raw row to per-store table via StoreRepo (Supabase).
     Load cache by URL. Call DeltaDetector.detect().
     Call EventSender.send_event() for each event.
     Update parse_cache after successful send.

   infrastructure/middlewares/ratelimit_middleware.py
     Track response_time deque(10) per domain.
     If latest > 3x median: multiply DOWNLOAD_DELAY by 1.5.
     If status==200 and len(body)<500: IgnoreRequest.

   infrastructure/middlewares/stealth_middleware.py
     Apply playwright_stealth on every Playwright page.

   infrastructure/middlewares/retry_middleware.py
     Retry on 429, 503, 520-522. Exponential backoff 2^n, max 5.
     Respect Retry-After header.

   infrastructure/db/supabase_client.py
     Singleton get_supabase() using SUPABASE_URL + SUPABASE_SERVICE_KEY.

   infrastructure/db/store_repo.py
     STORE_TABLE_MAP → upsert_product(source, data) per-store tables (on_conflict url).

   infrastructure/db/parse_cache_repo.py
     Supabase table parse_cache — same async method names as before.
     get_by_url, upsert, update_crm_ids, mark_parsed, get_stale.
     On PostgREST errors: log [SUPABASE_ERROR], raise DBError.

   infrastructure/db/event_repo.py
     Supabase table pending_events — save_pending, get_pending, mark_sent,
     mark_failed, increment_retry (RPC increment_retry in Postgres).

   infrastructure/db/session.py
     get_psycopg_connection() for optional direct sync SQL (Scrapy / tooling).

   Schema: PostgreSQL on Supabase; Alembic revision 001_initial_schema.py
   creates tables. No SQLAlchemy ORM models in app code.

4. CONFIG

   config/settings.py — Settings(BaseSettings) with all env vars.
   config/scrapy_settings.py — complete Scrapy settings.
   config/processor_aliases.json — 30+ real processor aliases.

5. DATABASE MIGRATIONS

   infrastructure/db/migrations/env.py — Alembic sync env, target_metadata = empty MetaData().
   infrastructure/db/migrations/versions/001_initial_schema.py
     Creates ALL tables with indexes. Downgrade drops all.
   After first upgrade against Supabase, run migrations/versions/002_supabase_functions.sql
   in Supabase SQL Editor (Postgres function increment_retry for atomic retry_count).

6. TASKS

   tasks/celery_app.py
     Beat schedule:
     - fast_parse_all:  every 2 hours
     - full_parse_all:  weekly Sunday 00:00
     - discover_all:    daily 03:00
     - retry_pending:   every 5 minutes

   tasks/parse_tasks.py
     fast_parse_all(), full_parse_all(), discover_all()
     Each: loop all stores, call orchestrator, log results.

   tasks/event_tasks.py
     retry_pending(): load pending_events, batch send, update status.

7. TESTS SCAFFOLD

   tests/conftest.py — fixtures: db_session, mock_crm_client,
     sample_raw_product, sample_parse_cache
   tests/canary/canary_products.py — CANARY_PRODUCTS dict, 2 real URLs

8. ROOT FILES

   alembic.ini, scrapy.cfg, .gitignore

=== RULES ===
- Scraper NEVER imports from or connects to CRM database
- parse_cache is updated ONLY after successful CRM API response
- DeltaDetector returns [] when nothing changed — no event sent
- All normalizers handle None input gracefully (return None)
- LLMExtractor is gated by settings.LLM_EXTRACTION_ENABLED
- Output every file completely. No truncation. No stubs.
```

---

## РАЗДЕЛ 1 — Спайдеры

### Итерация 1.1 — Mediapark spider
```
Context: Read PROJECT.md fully. Read infrastructure/spiders/base.py.

Mediapark.uz is a static HTML store. It has a structured spec table
which is the best source of characteristics.

Task: Implement infrastructure/spiders/mediapark.py

Requirements:
- MediaparkSpider(BaseProductSpider), store_name = "mediapark"
- start_category_urls: real mediapark.uz URLs for phones, laptops, TVs,
  tablets, appliances.

- discover_urls(response) → list[str]:
    Extract all product detail URLs from a category/listing page.
    Handle pagination via get_next_page(response).
    Call _zero_result_guard and _infinite_pagination_guard.

- fast_parse_item(response) → dict:
    Extract ONLY: price_str, in_stock, url.
    Price: find current price element, handle crossed-out (original) price.
    in_stock: detect "нет в наличии" / "out of stock" patterns.
    This must be fast — no heavy DOM traversal.

- full_parse_item(response) → dict:
    Extract: title, brand, all spec table rows, all image URLs,
    external_id (from URL or page), price_str, in_stock.
    SPEC_FIELD_MAP: complete mapping of all Russian spec table
    labels on mediapark.uz → domain field names (25+ entries).
    Unknown rows → raw['_unknown_fields'][label] = value (never drop).
    Images: prefer full-resolution URLs, handle data-src lazy loading.

- Canary: add mediapark entry to tests/canary/canary_products.py
  with a real Samsung phone URL and assertions.

Output the complete file.
```

### Итерация 1.2 — OLX spider
```
Context: Read PROJECT.md and infrastructure/spiders/base.py.

OLX Uzbekistan (olx.uz) is a classifieds marketplace.
No spec table — description is the only source of specs.
Multiple sellers post the same product independently.

Task: Implement infrastructure/spiders/olx.py

Requirements:
- OlxSpider(BaseProductSpider), store_name = "olx"
- Categories: smartphones, laptops, TVs, tablets. Real olx.uz URLs.

- discover_urls(response): extract product URLs, page-based pagination.

- fast_parse_item(response):
    price_str: from .price-label element.
    Handle "Договорная" → mark as ON_REQUEST in raw.
    in_stock: OLX listings are assumed in_stock unless marked otherwise.

- full_parse_item(response):
    title: from h1.
    description: full text — primary spec source for OLX.
    seller_type: "private" or "business".
    images: from JSON-LD schema or og:image meta tags.
    location: city name (store in raw for CRM).
    is_bundle: detect "комплект"/"набор"/"+ чехол" → raw['is_bundle']=True.
    Set raw['spec_source'] = 'description' so normalize_pipeline
    knows to skip StructuredExtractor and go straight to regex.

- Canary: add olx entry.

Output complete file.
```

### Итерация 1.3 — Texnomart spider
```
Context: Read PROJECT.md. Read mediapark.py as reference.
Texnomart.uz has mixed JS — some pages need Playwright.

Task: Implement infrastructure/spiders/texnomart.py

Requirements:
- TexnomartSpider(BaseProductSpider), store_name = "texnomart"
- use_playwright = True only for detail pages (saves resources on listings).
- custom_settings: PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000

- fast_parse_item: works without Playwright (prices visible in listing HTML).

- full_parse_item (with Playwright):
    Wait for CSS selector of spec table before extracting.
    Handle cookie consent popup: click if present.
    SPEC_FIELD_MAP: texnomart uses BOTH Russian and Uzbek labels —
    cover both. E.g. "Xotira" = "storage_gb", "Batareya" = "battery_mah".
    Extract installment price separately if shown (store in raw).
    Detect "Нет в наличии" → in_stock = False.

- Canary: add texnomart entry.

Output complete file.
```

### Итерация 1.4 — Makro spider
```
Context: Read PROJECT.md, infrastructure/spiders/base.py.
Makro.uz exposes a REST JSON API.

Task: Implement infrastructure/spiders/makro.py

Requirements:
- MakroSpider(BaseProductSpider), store_name = "makro"
- API-based: use Scrapy Request with JSON response parsing.
- Use real makro.uz API endpoints for listing and detail.
  Inspect the actual API calls at makro.uz to find endpoints.
  If REST: GET /api/catalog/products?categoryId=X&page=N&limit=48
  If GraphQL: adapt accordingly.

- discover_urls: yield API requests for each product detail endpoint.

- fast_parse_item: extract price + in_stock from API response JSON.

- full_parse_item: extract all available fields from API JSON.
  Specs come as array [{name, value}] — map to SPEC_FIELD_MAP.

- Handle 429: extract Retry-After header, respect it.

- Canary: add makro entry.

Output complete file.
```

### Итерация 1.5 — Uzum spider (GraphQL)
```
Context: Read PROJECT.md fully. Read all existing spiders.
Uzum.uz is a React SPA with GraphQL. Most complex spider.

Task: Implement infrastructure/spiders/uzum.py AND
infrastructure/middlewares/uzum_graphql_middleware.py

Strategy: intercept GraphQL network responses via Playwright's
page.on('response') instead of parsing React DOM.

uzum_graphql_middleware.py:
  On every Playwright page load, register a response handler that:
  - Captures responses where URL contains "/api/storefront"
    and Content-Type is application/json
  - Parses JSON, stores in response.meta['graphql_payloads'] list
  - Handles malformed JSON silently (try/except)

uzum.py:
- UzumSpider(BaseProductSpider), store_name = "uzum"
- use_playwright = True + uses graphql middleware

- discover_urls (with Playwright):
    Scroll to bottom 3 times to trigger lazy loading:
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    Sleep 1s between scrolls.
    Extract product links.

- fast_parse_item:
    Try GraphQL payloads first for price + in_stock.
    Fall back to DOM if payload empty.

- full_parse_item:
    Extract from graphql_payloads:
      Try data.makeSearch.items[].catalogItem
      Try data.getProductInfo
    Fall back to DOM parsing if both empty.
    Description is primary spec source → set raw['spec_source']='description'
    If completeness_score < 0.4 after regex → set raw['needs_llm']=True
    Color: detect from active swatch element or GraphQL payload.
    Region variant: detect "Global"/"EU version" in title/description.
    Images: prefer GraphQL payload URLs (highest resolution).

- Canary: add uzum entry.

Output both files completely.
```

---

## РАЗДЕЛ 2 — Delta & CRM Integration

### Итерация 2.1 — Delta detector
```
Context: Read PROJECT.md sections "Алгоритм парсинга" and
"API взаимодействие с CRM". Read domain/events.py,
infrastructure/db/parse_cache_repo.py.

Task: Implement application/delta_detector.py completely.

The delta detector is the CORE of the scraper's value.
It answers: "what changed since we last scraped this URL?"

DeltaDetector class:

  detect(normalized: NormalizedProduct, cache: ParseCache | None,
         crm_response: CRMSyncResponse | None = None) -> list[BaseEvent]:

    If cache is None (new product):
      Return [ProductFoundEvent(
        source=normalized.source,
        source_url=normalized.url,
        source_id=normalized.source_id,
        crm_product_id=crm_response.crm_product_id if crm_response else None,
        product=ProductPayload(name=..., brand=..., characteristics=specs_dict),
        listing=ListingPayload(price=..., currency=..., in_stock=..., parsed_at=...)
      )]

    If cache exists:
      events = []

      Price changed (use tolerance: abs(new - old) > 100 UZS):
        events.append(PriceChangedEvent(
          crm_listing_id=cache.crm_listing_id,
          listing=ListingPayload(new price, in_stock, parsed_at)
        ))

      in_stock changed to False:
        events.append(OutOfStockEvent(
          crm_listing_id=cache.crm_listing_id,
          parsed_at=now()
        ))

      in_stock changed back to True:
        events.append(PriceChangedEvent(...))  # reuse to update listing

      New characteristics discovered (fields that were null before):
        new_chars = {k:v for k,v in specs_dict.items()
                     if v is not None and cache does not have this field}
        if new_chars:
          events.append(CharacteristicAddedEvent(
            crm_product_id=cache.crm_product_id,
            characteristics=new_chars
          ))

      If events == []: return []  # nothing changed, send nothing

    Return events

  _specs_to_dict(specs: BaseSpecs) -> dict:
    Return only non-None fields (excluding meta fields like
    completeness_score, extraction_method, raw_fields).

  _price_changed(new: Decimal, old: Decimal, tolerance=100) -> bool:
    Return abs(new - old) > tolerance

Write unit tests in tests/unit/test_delta_detector.py:
  - test_new_product_returns_product_found
  - test_same_price_returns_empty
  - test_price_within_tolerance_returns_empty
  - test_price_changed_returns_event
  - test_went_out_of_stock
  - test_new_characteristic_discovered
  - test_multiple_events_at_once (price + new char)

Output both files completely.
```

### Итерация 2.2 — CRM client + event sender
```
Context: Read PROJECT.md section "API взаимодействие с CRM"
and "Обработка ошибок". Read domain/events.py.

Task: Implement application/crm_client.py AND application/event_sender.py

crm_client.py:
  CRMClient (uses httpx.AsyncClient):

  __init__: base_url from settings, headers with X-Parser-Key.
    timeout = httpx.Timeout(10.0).

  async sync_event(event: BaseEvent) -> CRMSyncResponse:
    POST /api/parser/sync with event.model_dump()
    On 200: return CRMSyncResponse(**response.json())
    On 4xx (not 429): log warning, return None
    On 429: wait Retry-After seconds (default 60), retry once
    On connection error/timeout: raise CRMUnavailableError

  async sync_batch(events: list[BaseEvent]) -> list[CRMSyncResponse]:
    Split into chunks of 100.
    POST /api/parser/sync/batch with {"events": [...]}
    On partial failure: collect successful responses, raise for failed.

  async find_in_catalog(source: str, source_id: str) -> CRMSyncResponse | None:
    GET /api/parser/catalog/find?source={source}&source_id={source_id}
    On 404: return None (product not in CRM yet)
    On error: log and return None (don't block scraping)

event_sender.py:
  EventSender:

  async send_event(event: BaseEvent) -> bool:
    Try crm_client.sync_event(event).
    On success (returns CRMSyncResponse with status="ok"): return True.
    On CRMUnavailableError:
      await event_repo.save_pending(event)
      log WARNING: [CRM_UNAVAILABLE] saved to pending_events
      return False
    On any other exception: same as above + log ERROR.

  async send_batch(events: list[BaseEvent]) -> tuple[int, int]:
    Returns (sent_count, failed_count).
    On partial CRM failure: save failed ones to pending_events.

  async flush_pending() -> tuple[int, int]:
    Load up to 100 pending events from event_repo.
    Send as batch via crm_client.sync_batch().
    Mark sent ones as 'sent', failed ones increment retry_count.
    If retry_count >= 10: mark as 'failed', send Sentry alert.
    Return (sent, failed).

Both files: comprehensive error handling, structured logging with
[CRM_SYNC], [CRM_BATCH], [CRM_RETRY] tags for easy grep.

Output both files completely.
```

---

## РАЗДЕЛ 3 — Нормализация

### Итерация 3.1 — Regex patterns + unit normalizer
```
Context: Read PROJECT.md section "Нормализация".
Read domain/specs/*.py for field names and types.

Task: Rewrite application/extractors/patterns.py and
application/extractors/unit_normalizer.py completely.

patterns.py:
  PHONE_PATTERNS, LAPTOP_PATTERNS, TV_PATTERNS — each field
  has 4+ patterns covering RU full, RU short, UZ, technical notation.
  Fields per category as listed in PROJECT.md specs schemas.
  Pre-compiled via compile_patterns() for performance.
  BOOLEAN_FIELDS = {"nfc", "wifi", "bluetooth", "hdmi"} — return True/False.

unit_normalizer.py:
  normalize_price(raw: str) -> Decimal | None
    Handle ALL formats:
      "2 990 000 сум" / "2,990,000" / "2990000"
      "2 990 000" (no unit — assume UZS)
      "По договорённости" / "по запросу" / "Narxi kelishiladi" → None
      "0" → None
      "" / None → None
    Remove non-digit chars except decimal separator, parse to Decimal.

  normalize_storage(raw: str) -> int | None  (always in GB)
    Handle TB: "1 TB" → 1024, "2TB" → 2048
    Handle: "256гб" / "256 GB" / "256ГБ" / "256gb"

  normalize_ram(raw: str) -> int | None  (GB)
    Same as storage but with sanity: if result > 64 → likely storage, return None

  normalize_display(raw: str) -> float | None  (inches)
    Handle comma: "6,7" → 6.7
    Handle cm: if unit is "см" or "cm" → divide by 2.54
    Handle explicit inch markers: дюйм/inch/"/″

  normalize_battery(raw: str) -> int | None  (mAh)
    Extract 3-5 digit number before mAh/мАч.

  normalize_weight_g(raw: str) -> int | None
    Handle g/г/gram/грамм, negative lookahead for гб.
    Handle kg: multiply by 1000.

  normalize_brand(raw: str, aliases: dict) -> str
    Lowercase, strip, lookup in aliases.
    BRAND_ALIASES covers 20+ brands with all RU/UZ variants.
    If not found: title-case the input.

  normalize_processor(raw: str, aliases: dict) -> str
    Lookup in processor_aliases.json.
    If not found: return cleaned title-case string.

  normalize_color(raw: str) -> str
    COLOR_MAP: Russian/Uzbek → canonical English color name.
    "чёрный"/"qora"/"black"/"Black Titanium" → normalize.

All functions: handle None input → return None.
Write comprehensive unit tests in tests/unit/test_unit_normalizer.py
covering edge cases for every function.

Output all files completely.
```

### Итерация 3.2 — Structured extractor + FIELD_ALIASES
```
Context: Read PROJECT.md "Нормализация". Read patterns.py,
unit_normalizer.py, domain/specs/*.py.

Task: Rewrite application/extractors/structured_extractor.py

FIELD_ALIASES dict (80+ entries):
  Map every known Russian/Uzbek spec table label to domain field.
  Cover: mediapark.uz (RU), texnomart.uz (RU + UZ), makro.uz (EN + RU).

  Examples (extend to 80+):
  "Оперативная память" → "ram_gb"
  "RAM" → "ram_gb"
  "Xotira" → "storage_gb"
  "Ichki xotira" → "storage_gb"
  "Batareya sig'imi" → "battery_mah"
  "Ekran o'lchami" → "display_size_inch"
  "Ekran turi" → "display_type"
  "Operatsion tizim" → "os"
  "Protsessor" → "processor"
  "Asosiy kamera" → "main_camera_mp"
  "Old kamera" → "front_camera_mp"
  "SIM kartalar soni" → "sim_count"
  "Og'irligi" → "weight_g"
  ... (cover all fields for phone, laptop, TV, appliance)

StructuredExtractor:
  extract(raw_specs: dict, schema_class: type[BaseSpecs]) -> BaseSpecs:
    For each (label, value) in raw_specs:
      1. Normalize label: lowercase, strip, collapse whitespace
      2. Lookup in FIELD_ALIASES (exact match first)
      3. If not found: try fuzzy_match (difflib, threshold=0.82)
         Log fuzzy matches with [FUZZY_MATCH] tag
      4. If found field: run appropriate normalizer for that type
      5. Sanity check: if ram_gb > 32 in phone context →
         log [SPEC_SANITY_SWAP], treat as storage_gb instead
      6. Unknown labels → specs.raw_fields['_unknown_fields'][label] = value

    After all fields: specs.completeness_score = specs.compute_score()
    specs.extraction_method = "structured"
    return specs

  fuzzy_match(label: str, threshold: float = 0.82) -> str | None:
    Uses difflib.SequenceMatcher against all FIELD_ALIASES keys.
    Returns best match key if ratio >= threshold, else None.

Output complete file.
```

---

## РАЗДЕЛ 4 — База данных

### Итерация 4.1 — Supabase repositories
```
Context: Read PROJECT.md sections "База данных парсера" and "15. Supabase specifics".

Task: Implement Supabase-backed persistence (no SQLAlchemy ORM in application code):

  infrastructure/db/supabase_client.py — get_supabase() singleton.
  infrastructure/db/store_repo.py — upsert_product(source, data) → per-store table.
  infrastructure/db/parse_cache_repo.py — async methods unchanged for callers:
    get_by_url, upsert, update_crm_ids, mark_parsed, get_stale.
    Use supabase-py; on APIError log [SUPABASE_ERROR] and raise DBError.
  infrastructure/db/event_repo.py — same public async interface:
    save_pending, get_pending, mark_sent, mark_failed, increment_retry
    (increment_retry via Postgres RPC function increment_retry).

Dependencies: supabase-py>=2, psycopg2-binary for direct sync connections if needed.

Output all files completely.
```

### Итерация 4.2 — Alembic migration
```
Context: Read PROJECT.md and existing infrastructure/db/migrations/versions/001_initial_schema.py.

Task: Keep / maintain initial Alembic migration.

File: infrastructure/db/migrations/versions/001_initial_schema.py

Creates ALL tables in FK-safe order (store tables, parse_cache, parse_logs,
parse_queue, pending_events). JSONB defaults '{}'. Downgrade drops all.

Update infrastructure/db/migrations/env.py:
  target_metadata = empty sqlalchemy.MetaData() (migrations are op.* only).
  Sync connection URL from settings.DATABASE_URL_SYNC (same value as SUPABASE_DB_URL).

After running alembic upgrade head against Supabase Postgres, run
migrations/versions/002_supabase_functions.sql in the Supabase SQL Editor
(or `python scripts/apply_supabase_functions.py`) so RPC `increment_retry` exists.
Supabase Storage is not used for scraper images.

Output migration files completely.
```

---

## РАЗДЕЛ 5 — Надёжность

### Итерация 5.1 — Все middlewares
```
Context: Read PROJECT.md sections "Anti-detection" and "Обработка ошибок".

Task: Implement ALL middlewares completely.

1. infrastructure/middlewares/ratelimit_middleware.py
   AdaptiveRateLimitMiddleware:
   - deque(maxlen=10) of response times per domain
   - If latest > 3x median: DOWNLOAD_DELAY *= 1.5, cap at 30s
     Log [RATE_LIMIT_SUSPECTED] domain + new delay
   - If status==200 and len(body) < 500: raise IgnoreRequest
     Log [EMPTY_BODY_200] url

2. infrastructure/middlewares/stealth_middleware.py
   Applies playwright_stealth.stealth_async(page) on Playwright pages.
   Sets viewport 1920x1080, overrides navigator.webdriver.
   Sets Accept-Language: ru-RU,ru;q=0.9,uz;q=0.8

3. infrastructure/middlewares/retry_middleware.py
   Extends Scrapy's RetryMiddleware.
   Retry statuses: 429, 503, 520, 521, 522.
   Exponential backoff: wait 2^retry_count seconds before retry.
   Max retries: 5.
   On 429: check Retry-After header, use it if present.

4. infrastructure/middlewares/mobile_redirect_middleware.py
   If response.url has "m." prefix and request.url did not:
   Retry with desktop User-Agent, dont_filter=True.
   Max 1 retry per request to prevent loop.

5. Update config/scrapy_settings.py:
   All middlewares in correct priority order with comments.
   PLAYWRIGHT settings for stealth.
   AUTOTHROTTLE settings.

Output all files completely.
```

### Итерация 5.2 — Canary system
```
Context: Read PROJECT.md "Canary система". Read all spiders.

Task: Build complete canary assertion system.

1. tests/canary/canary_products.py
   CANARY_PRODUCTS for all 5 stores.
   Each entry: url (real product), store, assertions dict.
   Assertions cover: brand, 2+ spec fields, price range in UZS,
   images count >= 1.

2. tasks/canary_tasks.py
   run_canary_checks() Celery task:
   For each store:
     Scrape canary URL using single-URL scrape runner.
     Check each assertion.
     On failure: log [CANARY_FAIL] store + field + expected + got.
     Capture to Sentry if SENTRY_DSN set.
   Return dict of results.

   deep_get(obj, path: str) utility:
     Supports dot notation: "specs.ram_gb" → obj.specs.ram_gb

3. Update tasks/celery_app.py: add hourly canary schedule.

Output all files completely.
```

---

## РАЗДЕЛ 6 — Финализация

### Итерация 6.1 — Integration tests
```
Context: Read ALL project files.

Task: Write integration tests in tests/integration/test_pipeline_e2e.py

Tests:

1. test_new_product_full_flow:
   Mock mediapark HTML with real-looking Samsung spec table.
   Run: spider → validate → normalize → delta_detector →
        mock CRM client → update parse_cache.
   Assert: ProductFoundEvent sent, parse_cache entry created,
   PhoneSpecs completeness > 0.7, price parsed correctly.

2. test_price_change_sends_delta:
   Existing parse_cache entry with price=10_000_000.
   Spider returns same product with price=9_500_000.
   Assert: PriceChangedEvent sent (not ProductFoundEvent),
   parse_cache updated to new price.

3. test_same_price_sends_nothing:
   Existing cache, same price, same in_stock.
   Assert: no events sent to CRM, CRM client not called.

4. test_crm_unavailable_saves_pending:
   CRM client raises CRMUnavailableError.
   Assert: event saved to pending_events with status='pending'.

5. test_retry_pending_events:
   3 pending events in DB, CRM now available.
   Call flush_pending().
   Assert: all 3 sent, marked as 'sent' in DB.

6. test_olx_regex_extraction:
   Mock OLX detail page with laptop description in Russian.
   Assert: LaptopSpecs extracted via regex, key fields filled,
   no LLM call made (regex was sufficient).

7. test_price_parsing_edge_cases:
   "2 990 000 сум" → 2990000
   "По договорённости" → None
   "0" → None
   "2,990,000" → 2990000

Use fakeredis for Redis. SQLite :memory: for DB.
Mock httpx for CRM calls.
pytest-asyncio for async tests.

Output complete file and updated conftest.py.
```

### Итерация 6.2 — README + Makefile
```
Context: Read PROJECT.md and all project files.

Task: Create README.md and Makefile.

README.md sections:
  - Quick Start (5 commands, copy-paste ready)
  - Architecture: scraper is a sensor, sends deltas to CRM
  - Three parse modes explained (fast/full/discover)
  - Adding a new store (checklist)
  - Configuration (.env reference)
  - Running manually (scrapy crawl commands)
  - Monitoring (canary, Sentry, parse_logs table)
  - Common issues on Windows (Poetry PATH, Docker not running)

Makefile targets:
  up, down, migrate, rollback, shell
  crawl store=mediapark, crawl-all
  fast-parse store=mediapark
  discover store=mediapark
  retry-events
  canary
  worker, beat
  test, test-unit, test-integration, test-canary
  lint, format
  db-shell, redis-cli
  logs store=mediapark
  pending — show count of pending_events by status

Output both files completely.
```
