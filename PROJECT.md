# UZ Tech Scraper — Project Documentation

> Полная документация для Cursor AI. Цель: скрапер технических товаров с маркетплейсов Узбекистана,
> построенный на доменной модели (DDD). Принцип: минимум самописного кода, максимум готовых решений.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Domain Model](#4-domain-model)
5. [Architecture Layers](#5-architecture-layers)
6. [Spider Implementation Guide](#6-spider-implementation-guide)
7. [Spec Extraction Pipeline](#7-spec-extraction-pipeline)
8. [Image Normalization Pipeline](#8-image-normalization-pipeline)
9. [Anti-Detection & Network](#9-anti-detection--network)
10. [Database Schema](#10-database-schema)
11. [Task Queue & Scheduling](#11-task-queue--scheduling)
12. [Edge Cases & Solutions](#12-edge-cases--solutions)
13. [Observability & Alerting](#13-observability--alerting)
14. [Development Priorities](#14-development-priorities)
15. [Environment & Dependencies](#15-environment--dependencies)

---

## 1. Project Overview

### What we're building
A scraper that collects **tech product data** (smartphones, laptops, TVs, appliances) from Uzbekistan's major online stores, normalizes it into a unified domain model, and stores it in PostgreSQL with full price history.

### Target stores
| Store | URL | Tech stack | Complexity |
|---|---|---|---|
| Mediapark | mediapark.uz | Server-rendered HTML | Low |
| OLX | olx.uz | Mostly static HTML | Low |
| Texnomart | texnomart.uz | Mixed JS | Medium |
| Makro | makro.uz | Paginated REST API | Medium |
| Uzum | uzum.uz | React SPA + GraphQL | High |

### Core principles
- **DDD first**: Domain layer has zero infrastructure dependencies
- **Minimum custom code**: Extend Scrapy middlewares, not reinvent them
- **Pydantic everywhere**: Validation at every boundary
- **Cascade extraction**: Structured fields → Regex → LLM (each step only if previous insufficient)
- **Idempotency**: Running the same scrape twice produces no duplicates

---

## 2. Tech Stack

### Core
| Component | Library | Why |
|---|---|---|
| Spider engine | `scrapy` | Built-in dedup, retry, pipelines, rate limiting |
| JS rendering | `scrapy-playwright` | Playwright integrated as Scrapy middleware |
| Schema validation | `pydantic v2` | Domain models + auto validation |
| Task queue | `celery` + `redis` | Scheduling + distributed execution |
| Database | `postgresql` + `asyncpg` | JSONB for specs, arrays for images |
| ORM | `sqlalchemy 2.0` (async) | Async-native, Alembic migrations |
| Deduplication | `scrapy-redis` | Redis-backed request dedup + bloom filter |

### Data extraction
| Component | Library | Why |
|---|---|---|
| Fast text search | `flashtext` | 50x faster than re for keyword extraction |
| HTML parsing | `parsel` (built into Scrapy) | XPath + CSS selectors |
| NLP (optional) | `spacy` ru model | Entity extraction from Russian descriptions |
| LLM extraction | `anthropic` SDK | Fallback for unstructured specs (Uzum) |

### Image pipeline
| Component | Library | Why |
|---|---|---|
| Image download | Scrapy `ImagesPipeline` | Built-in, handles dedup by checksum |
| Background removal | `rembg` | U2Net model, runs locally, no API cost |
| Image classification | `open_clip` | CLIP zero-shot: clean shot vs banner vs lifestyle |
| Image hashing | `imagehash` | Perceptual hash for visual dedup |

### Infrastructure
| Component | Tool | Why |
|---|---|---|
| Proxy rotation | `scrapy-rotating-proxies` | Auto-retry on blocked proxies |
| Anti-bot | `playwright-stealth` | Removes headless browser fingerprints |
| User-agent | `fake-useragent` | Realistic UA rotation |
| Migrations | `alembic` | Schema versioning |
| Monitoring | `scrapy` built-in stats + `sentry-sdk` | Error tracking |
| Config | `pydantic-settings` | Typed env vars |

---

## 3. Project Structure

```
uz_tech_scraper/
│
├── domain/                          # Zero external dependencies
│   ├── __init__.py
│   ├── product.py                   # Product, ProductVariant, ProductFamily
│   ├── price.py                     # Price, PriceRecord, currency handling
│   ├── category.py                  # Category enum + tree
│   ├── specs/                       # Canonical spec schemas per category
│   │   ├── base.py                  # BaseSpecs with completeness_score
│   │   ├── phone.py                 # PhoneSpecs(BaseSpecs)
│   │   ├── laptop.py                # LaptopSpecs(BaseSpecs)
│   │   ├── tv.py                    # TVSpecs(BaseSpecs)
│   │   └── appliance.py             # ApplianceSpecs(BaseSpecs)
│   ├── image.py                     # ProductImage, ImageType enum
│   └── events.py                    # ProductDiscovered, PriceChanged, SpecsUpdated
│
├── application/                     # Use cases, orchestration
│   ├── scrape_job.py                # ScrapeJob entity + state machine
│   ├── extractors/
│   │   ├── spec_extractor.py        # Cascade: structured → regex → LLM
│   │   ├── image_extractor.py       # Download, classify, rank
│   │   └── price_extractor.py       # Parse UZS prices, handle edge cases
│   ├── deduplicator.py              # Fingerprint logic, family detection
│   └── exporters/
│       ├── csv_exporter.py
│       └── webhook_exporter.py
│
├── infrastructure/
│   ├── spiders/
│   │   ├── base.py                  # BaseProductSpider — abstract
│   │   ├── mediapark.py
│   │   ├── olx.py
│   │   ├── texnomart.py
│   │   ├── makro.py
│   │   └── uzum.py                  # GraphQL interceptor
│   ├── pipelines/
│   │   ├── validate_pipeline.py     # Pydantic validation
│   │   ├── image_pipeline.py        # Download + classify + rembg
│   │   ├── dedup_pipeline.py        # Fingerprint + bloom filter
│   │   └── persist_pipeline.py      # Upsert to PostgreSQL
│   ├── middlewares/
│   │   ├── proxy_middleware.py      # Proxy rotation + health check
│   │   ├── stealth_middleware.py    # playwright-stealth injection
│   │   ├── ratelimit_middleware.py  # Adaptive rate limit by response time
│   │   └── retry_middleware.py      # Extended retry with backoff
│   ├── repositories/
│   │   ├── product_repo.py          # ProductRepository(PostgreSQL)
│   │   └── job_repo.py              # ScrapeJobRepository
│   └── db/
│       ├── models.py                # SQLAlchemy ORM models
│       └── migrations/              # Alembic versions
│
├── config/
│   ├── settings.py                  # pydantic-settings, all env vars
│   ├── scrapy_settings.py           # Scrapy settings.py
│   └── processor_aliases.json       # "SM8550" → "Snapdragon 8 Gen 2"
│
├── tasks/
│   ├── celery_app.py
│   └── scrape_tasks.py              # @app.task per store
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── canary/                      # Canary assertions per store
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── alembic.ini
```

---

## 4. Domain Model

### Core entities

```python
# domain/product.py
from __future__ import annotations
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field
from .category import Category
from .specs.base import BaseSpecs
from .image import ProductImage
from .price import PriceRecord

class ProductFamily(BaseModel):
    """Groups variants of the same model (e.g. iPhone 15 in all colors/storages)"""
    id: UUID = Field(default_factory=uuid4)
    brand: str
    model_name: str               # "iPhone 15"
    category: Category
    canonical_specs: Optional[BaseSpecs] = None   # best available specs

class ProductVariant(BaseModel):
    """One specific sellable SKU"""
    id: UUID = Field(default_factory=uuid4)
    family_id: UUID
    color: Optional[str] = None
    storage_gb: Optional[int] = None
    ram_gb: Optional[int] = None
    region_variant: Optional[str] = None     # "EU", "CN", "global" — grey imports
    sources: list[SourceRecord] = []
    images: list[ProductImage] = []
    specs: Optional[BaseSpecs] = None
    completeness_score: float = 0.0

class SourceRecord(BaseModel):
    """One store's listing for a variant"""
    store: str                    # "uzum", "mediapark", etc.
    url: str
    external_id: Optional[str] = None
    prices: list[PriceRecord] = []
    last_scraped_at: datetime
    is_available: bool = True
    is_bundle: bool = False       # "смартфон + чехол" → True
```

### Price model

```python
# domain/price.py
from decimal import Decimal
from enum import Enum

class Currency(str, Enum):
    UZS = "UZS"
    USD = "USD"

class PriceStatus(str, Enum):
    AVAILABLE    = "available"
    ON_REQUEST   = "on_request"    # "цена по запросу"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"

class Price(BaseModel):
    amount: Optional[Decimal] = None
    currency: Currency = Currency.UZS
    status: PriceStatus = PriceStatus.AVAILABLE
    original_amount: Optional[Decimal] = None   # зачёркнутая цена
    discount_pct: Optional[float] = None        # вычисляется автоматически

    @validator('discount_pct', always=True)
    def compute_discount(cls, v, values):
        a = values.get('amount')
        o = values.get('original_amount')
        if a and o and o > 0:
            return round((1 - float(a) / float(o)) * 100, 1)
        return None
```

### Spec schemas

```python
# domain/specs/base.py
class BaseSpecs(BaseModel):
    completeness_score: float = 0.0
    extraction_method: str = "unknown"   # "structured", "regex", "llm"
    raw_fields: dict = {}                # unparsed fields for debugging

    def compute_score(self) -> float:
        """Ratio of non-None fields to total declared fields"""
        fields = self.__fields__
        excluded = {'completeness_score', 'extraction_method', 'raw_fields'}
        filled = sum(1 for f, _ in fields.items()
                     if f not in excluded and getattr(self, f) is not None)
        total = len(fields) - len(excluded)
        return round(filled / total, 2) if total > 0 else 0.0

# domain/specs/phone.py
class PhoneSpecs(BaseSpecs):
    display_size_inch: Optional[float] = None
    display_resolution: Optional[str] = None    # "2400x1080"
    display_type: Optional[str] = None          # "AMOLED", "IPS"
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    battery_mah: Optional[int] = None
    processor: Optional[str] = None             # normalized via aliases
    processor_cores: Optional[int] = None
    main_camera_mp: Optional[int] = None
    front_camera_mp: Optional[int] = None
    os: Optional[str] = None
    sim_count: Optional[int] = None
    nfc: Optional[bool] = None
    weight_g: Optional[int] = None

# domain/specs/laptop.py
class LaptopSpecs(BaseSpecs):
    display_size_inch: Optional[float] = None
    display_resolution: Optional[str] = None
    processor: Optional[str] = None
    processor_cores: Optional[int] = None
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    storage_type: Optional[str] = None         # "SSD", "HDD", "NVMe"
    gpu: Optional[str] = None
    os: Optional[str] = None
    battery_wh: Optional[float] = None
    weight_kg: Optional[float] = None
    usb_c_count: Optional[int] = None
    hdmi: Optional[bool] = None
```

---

## 5. Architecture Layers

### Flow: Raw HTML → Normalized Product

```
Spider.parse()
  → yields RawProductItem (dict)
  → ValidatePipeline     (Pydantic: required fields present)
  → SpecExtractorPipeline (cascade extraction → BaseSpecs)
  → ImagePipeline        (download → classify → rembg if needed → rank)
  → DedupPipeline        (fingerprint → bloom filter check)
  → PersistPipeline      (upsert ProductVariant + SourceRecord + PriceRecord)
```

### Pipeline execution order in scrapy_settings.py

```python
ITEM_PIPELINES = {
    'infrastructure.pipelines.validate_pipeline.ValidatePipeline':     100,
    'infrastructure.pipelines.image_pipeline.ProductImagePipeline':    200,
    'infrastructure.pipelines.dedup_pipeline.DedupPipeline':           300,
    'infrastructure.pipelines.persist_pipeline.PersistPipeline':       400,
}
```

---

## 6. Spider Implementation Guide

### BaseProductSpider

```python
# infrastructure/spiders/base.py
import scrapy
from abc import abstractmethod
from domain.product import ProductVariant

class BaseProductSpider(scrapy.Spider):
    # Subclasses MUST define:
    store_name: str = ""
    start_category_urls: dict[str, str] = {}   # {category_slug: url}

    custom_settings = {
        'DOWNLOAD_DELAY': 1.5,
        'RANDOMIZE_DOWNLOAD_DELAY': True,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2,
    }

    @abstractmethod
    def parse_product_list(self, response) -> list[str]:
        """Return list of product detail URLs from a listing page"""
        ...

    @abstractmethod
    def parse_product_detail(self, response) -> dict:
        """Return raw product dict from detail page"""
        ...

    def parse(self, response):
        # Zero-result guard
        urls = self.parse_product_list(response)
        if not urls and response.meta.get('page', 1) == 1:
            self.logger.warning(f"[ZERO_RESULT] {response.url} — possible parser break")
            return

        for url in urls:
            yield scrapy.Request(url, callback=self._parse_detail_safe)

        # Pagination — with infinite loop guard
        next_url = self.get_next_page(response)
        if next_url and not self._is_duplicate_page(response, next_url):
            yield scrapy.Request(next_url, callback=self.parse,
                                 meta={'page': response.meta.get('page', 1) + 1})

    def _is_duplicate_page(self, response, next_url) -> bool:
        """Bloom filter check on first 5 product URLs to detect infinite pagination"""
        ...

    def _parse_detail_safe(self, response):
        try:
            yield self.parse_product_detail(response)
        except Exception as e:
            self.logger.error(f"[PARSE_ERROR] {response.url}: {e}", exc_info=True)
```

### Uzum spider (GraphQL interceptor)

```python
# infrastructure/spiders/uzum.py
# Uzum is a React SPA — DOM parsing is unreliable.
# Instead: intercept GraphQL network responses via Playwright.

class UzumSpider(BaseProductSpider):
    store_name = "uzum"
    use_playwright = True

    custom_settings = {
        **BaseProductSpider.custom_settings,
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 30000,
    }

    def parse_product_detail(self, response):
        # GraphQL response is already captured by the middleware
        # and stored in response.meta['graphql_data']
        data = response.meta.get('graphql_data', {})
        product = data.get('data', {}).get('makeSearch', {})
        # parse product from GraphQL payload
        ...

# infrastructure/middlewares/uzum_graphql_middleware.py
# Playwright page.on('response') interceptor that captures
# /api/storefront/v3/products/* responses and injects into meta
```

### Mediapark spider (structured fields — easiest)

```python
class MediaparkSpider(BaseProductSpider):
    store_name = "mediapark"

    SPEC_FIELD_MAP = {
        # table row label → domain field
        "Оперативная память":   "ram_gb",
        "Встроенная память":    "storage_gb",
        "Диагональ экрана":     "display_size_inch",
        "Ёмкость аккумулятора": "battery_mah",
        "Процессор":            "processor",
    }

    def parse_product_detail(self, response):
        raw = {}
        for row in response.css('table.specs-table tr'):
            label = row.css('td.label::text').get('').strip()
            value = row.css('td.value::text').get('').strip()
            field = self.SPEC_FIELD_MAP.get(label)
            if field:
                raw[field] = value
            else:
                # Log unknown fields — do NOT drop them
                raw.setdefault('_unknown_fields', {})[label] = value
        return raw
```

---

## 7. Spec Extraction Pipeline

### Cascade strategy

```python
# application/extractors/spec_extractor.py

SCORE_THRESHOLD_STRUCTURED = 0.7
SCORE_THRESHOLD_REGEX       = 0.4

def extract_specs(raw: dict, category: Category) -> BaseSpecs:
    schema_class = CATEGORY_SCHEMA_MAP[category]

    # Strategy 1: structured field mapping
    specs = StructuredExtractor(schema_class).extract(raw)
    specs.completeness_score = specs.compute_score()
    if specs.completeness_score >= SCORE_THRESHOLD_STRUCTURED:
        specs.extraction_method = "structured"
        return specs

    # Strategy 2: regex over description
    description = raw.get('description', '') + ' ' + raw.get('title', '')
    specs = RegexExtractor(schema_class).enrich(specs, description)
    specs.completeness_score = specs.compute_score()
    if specs.completeness_score >= SCORE_THRESHOLD_REGEX:
        specs.extraction_method = "regex"
        return specs

    # Strategy 3: LLM — only when cheaper than missing data
    # Result is cached by sha256(description) to avoid re-calling
    specs = LLMExtractor(schema_class).enrich(specs, description)
    specs.extraction_method = "llm"
    return specs
```

### Regex patterns (bilingual RU + UZ)

```python
# application/extractors/patterns.py
PHONE_PATTERNS = {
    "ram_gb": [
        r"(\d+)\s*(?:GB|ГБ|гб)\s*(?:RAM|ОЗУ|оперативн)",
        r"(\d+)\s*GB\s*RAM",
        r"(\d+)\s*GB\s*xotira\s*\(",    # Uzbek: "8 GB xotira (RAM)"
    ],
    "storage_gb": [
        r"(\d+)\s*(?:GB|ГБ)\s*(?:ROM|встроен|хранен|ichki)",
        r"(\d+)\s*(?:TB|ТБ)\s*(?:ROM|встроен)",  # terabyte edge case
    ],
    "display_size_inch": [
        r"(\d+[.,]\d+)\s*(?:дюйм|\"|\u2033|inch|dyuym)",
        r"диагональ[^\d]*(\d+[.,]\d+)",
    ],
    "battery_mah": [
        r"(\d{3,5})\s*(?:mAh|мАч|мah)",
    ],
    "weight_g": [
        r"(\d{2,4})\s*(?:г(?!б)|gram|грамм)",  # negative lookahead: not "гб"
    ],
}

# Use flashtext for keyword matching (50x faster than re for bulk text)
from flashtext import KeywordProcessor
processor = KeywordProcessor(case_sensitive=False)
```

### Unit normalization

```python
# application/extractors/unit_normalizer.py

def normalize_storage(raw: str) -> Optional[int]:
    """Convert any storage string to GB as int"""
    raw = raw.strip().replace(',', '.').replace(' ', '')
    if m := re.search(r'(\d+\.?\d*)\s*TB', raw, re.I):
        return int(float(m.group(1)) * 1024)
    if m := re.search(r'(\d+)\s*GB', raw, re.I):
        return int(m.group(1))
    return None

def normalize_processor(raw: str, aliases: dict) -> str:
    """Normalize processor name using aliases map"""
    # aliases loaded from config/processor_aliases.json
    # e.g. {"SM8550": "Snapdragon 8 Gen 2", "SM8550-AB": "Snapdragon 8 Gen 2"}
    raw_clean = raw.strip()
    return aliases.get(raw_clean, raw_clean)
```

### LLM extraction prompt

```python
LLM_SPEC_PROMPT = """
You are extracting technical specifications from a product description.
Category: {category}
Description (Russian or Uzbek): {description}

Return ONLY a JSON object matching this schema. Use null for unknown fields.
Schema: {schema_json}

Rules:
- RAM and storage must be numbers in GB (integer)
- Display size must be a float in inches (convert cm if needed)  
- Battery must be an integer in mAh
- processor: use the marketing name, not model number
- Return ONLY valid JSON, no explanation
"""
```

---

## 8. Image Normalization Pipeline

### Classification with CLIP

```python
# application/extractors/image_extractor.py
import open_clip
import torch
from PIL import Image

class ImageClassifier:
    LABELS = [
        "a clean product photo on white or light background",
        "a marketing banner with promotional text and graphics",
        "a lifestyle photo showing product in real-world context",
        "a photo of product accessories or packaging only",
    ]

    def __init__(self):
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            'ViT-B-32', pretrained='openai'
        )
        self.tokenizer = open_clip.get_tokenizer('ViT-B-32')
        self.text_tokens = self.tokenizer(self.LABELS)

    def classify(self, image_path: str) -> tuple[str, float]:
        image = self.preprocess(Image.open(image_path)).unsqueeze(0)
        with torch.no_grad():
            image_features = self.model.encode_image(image)
            text_features  = self.model.encode_text(self.text_tokens)
            probs = (image_features @ text_features.T).softmax(dim=-1)
        idx = probs.argmax().item()
        return self.LABELS[idx], float(probs[0][idx])
```

### Scoring and ranking

```python
def score_image(img_meta: dict, clip_label: str, clip_conf: float) -> float:
    score = 0.0
    # Clean product shot — best
    if "clean product" in clip_label and clip_conf > 0.6:
        score += 2.0
    # Resolution bonus
    w, h = img_meta.get('width', 0), img_meta.get('height', 0)
    if min(w, h) >= 800:
        score += 1.0
    # Aspect ratio bonus (1:1 or 4:3 preferred for tech products)
    if w > 0 and h > 0:
        ratio = w / h
        if 0.9 <= ratio <= 1.1 or 1.2 <= ratio <= 1.4:
            score += 0.5
    # rembg processed
    if img_meta.get('bg_removed') and img_meta.get('rembg_confidence', 0) > 0.7:
        score += 1.0
    return score

def process_images(urls: list[str], max_keep: int = 5) -> list[ProductImage]:
    results = []
    seen_hashes = set()

    for url in urls:
        path = download_image(url)
        if not path:
            continue

        # Perceptual dedup
        ph = str(imagehash.phash(Image.open(path)))
        if ph in seen_hashes:
            continue
        seen_hashes.add(ph)

        # Classify
        label, conf = classifier.classify(path)

        # Attempt background removal for marketing banners
        bg_removed = False
        rembg_conf = 0.0
        if "marketing banner" in label or "lifestyle" in label:
            cleaned_path, rembg_conf = try_remove_background(path)
            if rembg_conf > 0.7:
                path = cleaned_path
                bg_removed = True

        score = score_image(
            {'width': ..., 'height': ..., 'bg_removed': bg_removed, 'rembg_confidence': rembg_conf},
            label, conf
        )

        results.append(ProductImage(
            url=url,
            local_path=path,
            score=score,
            image_type=map_label_to_type(label),
            is_processed=bg_removed,
        ))

    return sorted(results, key=lambda x: x.score, reverse=True)[:max_keep]
```

### Edge cases: image-specific

| Problem | Detection | Solution |
|---|---|---|
| Lazy-loaded img.src="" | src is empty string or data:// | Use Playwright `wait_for_selector('img[src*="http"]')` |
| CDN placeholder on 404 | phash matches known placeholder hash | Maintain blocklist of placeholder hashes |
| WebP not supported | Check Content-Type header | Pillow handles WebP; ensure `pillow[webp]` installed |
| Watermark on product | CLIP detects text overlay | Store as-is, flag `has_watermark=True`; rembg won't help |
| Accessories photo | CLIP: "accessories or packaging" | Score = 0, include only if no other images |
| All variants share one image | Same URL across multiple variants | Don't deduplicate by URL across variants, only within |

---

## 9. Anti-Detection & Network

### Scrapy settings for anti-detection

```python
# config/scrapy_settings.py

# Playwright stealth — always enabled for JS spiders
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--disable-blink-features=AutomationControlled"],
}

# Rotating proxies
ROTATING_PROXY_LIST_PATH = '/etc/proxies.txt'
ROTATING_PROXY_BACKOFF_BASE = 2
ROTATING_PROXY_BACKOFF_CAP = 3600

# Adaptive throttle — key defense against soft rate limiting
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# Realistic browser headers
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
}

DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'scrapy_useragents.downloadermiddlewares.useragents.UserAgentsMiddleware': 400,
    'scrapy_rotating_proxies.middlewares.RotatingProxyMiddleware': 610,
    'infrastructure.middlewares.ratelimit_middleware.AdaptiveRateLimitMiddleware': 700,
    'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler': 800,
}
```

### Adaptive rate limit middleware

```python
# infrastructure/middlewares/ratelimit_middleware.py
# Detects soft rate limiting (no 429, just slow responses)

class AdaptiveRateLimitMiddleware:
    WINDOW = 10           # last N responses
    SLOW_THRESHOLD = 3.0  # x baseline = slow

    def __init__(self):
        self.response_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.WINDOW))

    def process_response(self, request, response, spider):
        domain = urlparse(request.url).netloc
        elapsed = response.meta.get('download_latency', 0)
        times = self.response_times[domain]
        times.append(elapsed)

        if len(times) == self.WINDOW:
            baseline = sorted(times)[len(times) // 2]  # median
            if elapsed > baseline * self.SLOW_THRESHOLD:
                current = spider.settings.getfloat('DOWNLOAD_DELAY', 1.0)
                spider.settings.set('DOWNLOAD_DELAY', min(current * 1.5, 30.0))
                spider.logger.warning(f"[RATE_LIMIT_SUSPECTED] {domain}, delay → {current * 1.5:.1f}s")

        # Detect 200 + empty body (another soft block pattern)
        if response.status == 200 and len(response.body) < 500:
            spider.logger.warning(f"[EMPTY_BODY_200] {request.url}")
            raise IgnoreRequest()

        return response
```

### Mobile redirect guard

```python
# Some UZ sites redirect to m.site.uz based on User-Agent
# Solution: always use desktop UA and follow redirects explicitly

REDIRECT_MAX_TIMES = 5
REDIRECT_ENABLED = True

def process_response(self, request, response, spider):
    if 'm.' in response.url and 'm.' not in request.url:
        # Was redirected to mobile — retry with desktop UA
        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        return request.replace(url=request.url, headers={'User-Agent': desktop_ua},
                               dont_filter=True)
```

---

## 10. Database Schema

### Core tables

```sql
-- Product family (groups variants of same model)
CREATE TABLE product_families (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand       TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    category    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(brand, model_name, category)
);

-- Specific sellable variant
CREATE TABLE product_variants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id           UUID REFERENCES product_families(id),
    color               TEXT,
    storage_gb          INT,
    ram_gb              INT,
    region_variant      TEXT,       -- "EU", "CN", "global"
    specs               JSONB,      -- PhoneSpecs / LaptopSpecs / etc.
    completeness_score  FLOAT DEFAULT 0,
    fingerprint         TEXT UNIQUE, -- sha256(brand+model+color+storage+ram)
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Per-store listing
CREATE TABLE source_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id      UUID REFERENCES product_variants(id),
    store           TEXT NOT NULL,
    url             TEXT NOT NULL,
    external_id     TEXT,
    is_available    BOOLEAN DEFAULT true,
    is_bundle       BOOLEAN DEFAULT false,
    last_scraped_at TIMESTAMPTZ,
    UNIQUE(store, url)
);

-- Price history (append-only)
CREATE TABLE price_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID REFERENCES source_records(id),
    amount          NUMERIC(15, 2),
    currency        TEXT DEFAULT 'UZS',
    original_amount NUMERIC(15, 2),  -- crossed-out price
    status          TEXT DEFAULT 'available',
    scraped_at      TIMESTAMPTZ DEFAULT now()
);

-- Images
CREATE TABLE product_images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id      UUID REFERENCES product_variants(id),
    url             TEXT NOT NULL,
    local_path      TEXT,
    image_type      TEXT,           -- "clean_shot", "banner", "lifestyle"
    score           FLOAT DEFAULT 0,
    is_processed    BOOLEAN DEFAULT false,  -- rembg applied
    has_watermark   BOOLEAN DEFAULT false,
    width           INT,
    height          INT,
    phash           TEXT            -- perceptual hash for dedup
);

-- Scrape jobs
CREATE TABLE scrape_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store       TEXT NOT NULL,
    category    TEXT,
    status      TEXT DEFAULT 'pending',   -- pending/running/done/failed
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    items_found INT DEFAULT 0,
    errors      INT DEFAULT 0,
    meta        JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_variants_family    ON product_variants(family_id);
CREATE INDEX idx_variants_specs     ON product_variants USING gin(specs);
CREATE INDEX idx_prices_source      ON price_records(source_id, scraped_at DESC);
CREATE INDEX idx_sources_store      ON source_records(store, is_available);
CREATE INDEX idx_images_variant     ON product_images(variant_id, score DESC);
```

### Fingerprint logic

```python
# application/deduplicator.py
import hashlib

def make_variant_fingerprint(brand: str, model: str, color: str | None,
                              storage_gb: int | None, ram_gb: int | None) -> str:
    def normalize(s: str | None) -> str:
        if not s: return ""
        return s.lower().strip().replace(" ", "_")

    parts = [
        normalize(brand),
        normalize(model),
        normalize(color),
        str(storage_gb or ""),
        str(ram_gb or ""),
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

---

## 11. Task Queue & Scheduling

### Celery setup

```python
# tasks/celery_app.py
from celery import Celery
from celery.schedules import crontab

app = Celery('uz_scraper', broker='redis://localhost:6379/0',
             backend='redis://localhost:6379/1')

app.conf.beat_schedule = {
    'scrape-mediapark-daily': {
        'task': 'tasks.scrape_tasks.run_spider',
        'schedule': crontab(hour=2, minute=0),
        'args': ('mediapark',),
    },
    'scrape-uzum-daily': {
        'task': 'tasks.scrape_tasks.run_spider',
        'schedule': crontab(hour=3, minute=0),
        'args': ('uzum',),
    },
    'canary-check-hourly': {
        'task': 'tasks.scrape_tasks.run_canary_checks',
        'schedule': crontab(minute=0),
    },
}

# tasks/scrape_tasks.py
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

@app.task(bind=True, max_retries=3)
def run_spider(self, store_name: str):
    try:
        process = CrawlerProcess(get_project_settings())
        spider_class = SPIDER_REGISTRY[store_name]
        process.crawl(spider_class)
        process.start()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
```

---

## 12. Edge Cases & Solutions

### Data / product level

| Edge case | Problem | Solution |
|---|---|---|
| Variant cards | iPhone 15 128GB black and 256GB blue are separate URLs | `ProductFamily` + `ProductVariant` domain split; family fingerprint = brand+model, variant adds color+storage |
| Bundle listings | "Смартфон + чехол" at combined price | Detect keywords (`"комплект"`, `"набор"`, `"+"` in title) → `is_bundle=True`, skip from price comparison |
| Discontinued URL returns 200 | Product removed but page exists | Check for "нет в наличии" / "товар снят" → `status=DISCONTINUED` |
| "По договорённости" price | Non-numeric price string | `PriceStatus.ON_REQUEST` — valid domain state, not an error |
| Crossed-out price ambiguity | Is it real original or fake "sale"? | Store both `amount` and `original_amount`; compute `discount_pct`; consumer decides trust |
| Same SKU at multiple sellers | OLX has 10 sellers for same phone | One `ProductVariant`, multiple `SourceRecord` entries |
| Grey import | Same model, different firmware/region | Detect region markers in title/description → `region_variant` field |

### Spec level

| Edge case | Problem | Solution |
|---|---|---|
| RAM/storage swapped | Seller writes "256GB RAM, 8GB memory" | Sanity bounds: RAM > 32GB → likely storage; swap with warning |
| Same processor, different names | "SM8550" = "Snapdragon 8 Gen 2" | `config/processor_aliases.json` — maintained lookup table |
| Comma as decimal separator | "6,7 дюйма" | Replace `,` → `.` before float parse — always |
| UZ language specs | "8 GB xotira" | Bilingual regex patterns for all fields |
| Specs updated by seller | RAM was wrong, now corrected | Store `updated_at`, log `SpecsUpdated` event, keep history in JSONB array |
| Unknown spec table fields | Mediapark adds new row | Log to `raw_fields['_unknown']`, never raise exception |

### Image level

| Edge case | Problem | Solution |
|---|---|---|
| Lazy-loaded images | `img.src` is empty until scroll | Playwright: `await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")` |
| CDN 404 returns placeholder | Download succeeds but it's a gray square | Maintain `PLACEHOLDER_PHASHES` blocklist; skip matches |
| Variant shares parent image | All colors show same image | Don't deduplicate images across variants, only within one variant |
| Accessories photo taken as product | First photo shows case/charger | CLIP label "accessories or packaging" → score = 0; only use if nothing better |
| Watermark over product | Store brand watermark in corner | Flag `has_watermark=True`; rembg won't remove it reliably |
| rembg cuts into product | Model confidence < 0.7 | Use original image; discard rembg result |

### Network level

| Edge case | Problem | Solution |
|---|---|---|
| Soft rate limit (no 429) | Slow responses, no error code | `AdaptiveRateLimitMiddleware` — auto-increase delay on latency spike |
| 200 + empty body | Blocked but no error code | Check `len(response.body) < 500` → raise `IgnoreRequest()` |
| Mobile redirect | UA triggers m.site.uz redirect | Always use desktop UA; detect redirect pattern → retry |
| Session cookie expiry | Mid-crawl auth failure | Spider-level `session_refresh()` hook called on 401/403 |
| Infinite pagination | Last page re-serves itself | Bloom filter on first-5-products hash per page |
| Cursor-based GraphQL paging | `after` cursor, not `?page=N` | Store cursor from response, pass to next request |

### Operational level

| Edge case | Problem | Solution |
|---|---|---|
| Store redesign | All CSS selectors break overnight | **Canary assertions** (see below) — hourly check of known products |
| Zero-result listing page | Empty page looks like a normal page | Assert `len(products) > 0` on page 1; log WARNING if violated |
| One spider crashes | Blocks Celery worker | Each spider in isolated Celery task; `max_retries=3` |
| Holiday sale layout | Uzum adds banners on Navruz/New Year | Monitor `unknown_fields` rate; spike = likely structural change |
| Specs staleness | Price changes hourly, specs never re-scraped | Separate re-scrape schedules: prices daily, specs weekly |

### Canary assertion system

```python
# tests/canary/canary_products.py
CANARY_PRODUCTS = {
    "mediapark": {
        "url": "https://mediapark.uz/...",  # Samsung Galaxy S24
        "assertions": {
            "brand": "Samsung",
            "specs.ram_gb": 8,
            "specs.storage_gb": lambda v: v in [128, 256],
            "price.amount": lambda v: 5_000_000 < v < 20_000_000,
        }
    },
    "uzum": {
        "url": "https://uzum.uz/...",  # Apple iPhone 15
        "assertions": {
            "brand": "Apple",
            "specs.display_size_inch": lambda v: 6.0 < v < 6.3,
        }
    },
}

# tasks/scrape_tasks.py
@app.task
def run_canary_checks():
    for store, config in CANARY_PRODUCTS.items():
        result = scrape_single_product(config['url'], store)
        for field, expected in config['assertions'].items():
            actual = deep_get(result, field)
            ok = expected(actual) if callable(expected) else actual == expected
            if not ok:
                alert(f"[CANARY FAIL] {store} / {field}: got {actual!r}")
```

---

## 13. Observability & Alerting

### What to monitor

```python
# Key Scrapy stats to track per run:
CRITICAL_METRICS = {
    'item_scraped_count':       ('>', 0),         # must scrape something
    'item_dropped_count':       ('<', 50),         # too many drops = parser issue
    'downloader/exception_count': ('<', 100),
    'httperror/response_count': ('<', 20),
    'finish_reason':            ('==', 'finished'), # not 'shutdown' or 'closespider'
}

# Custom stats to add in pipelines:
# 'specs/completeness_avg'     — track extraction quality over time
# 'specs/llm_fallback_count'   — high number = regex patterns need updating
# 'images/clean_shot_pct'      — low number = CLIP model needs retraining
# 'images/rembg_applied_count'
```

### Sentry integration

```python
# infrastructure/spiders/base.py
import sentry_sdk
sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)

# In spider error handler:
def errback_httpbin(self, failure):
    sentry_sdk.capture_exception(failure.value)
    self.logger.error(repr(failure))
```

---

## 14. Development Priorities

### Phase 1 — Foundation (Week 1-2)
1. `domain/` layer — all Pydantic models, zero infra dependencies
2. `domain/specs/` — PhoneSpecs, LaptopSpecs (most common categories)
3. `BaseProductSpider` skeleton with canary assertion infrastructure
4. Database schema + Alembic migration
5. `ValidatePipeline` + `PersistPipeline`

### Phase 2 — First working spider (Week 2-3)
6. `MediaparkSpider` (simplest: static HTML, structured specs table)
7. Regex extractor + unit normalizer
8. `DedupPipeline` with fingerprinting
9. Basic Celery scheduling

### Phase 3 — Image pipeline (Week 3-4)
10. `ProductImagePipeline` with CLIP classification
11. `rembg` integration with confidence check
12. Image scoring + ranking

### Phase 4 — Remaining spiders (Week 4-6)
13. `OlxSpider`
14. `TexnomartSpider`
15. `MakroSpider`
16. `UzumSpider` with GraphQL interceptor (most complex — last)

### Phase 5 — Hardening (Week 6-7)
17. LLM extraction fallback
18. Adaptive rate limit middleware
19. Full canary assertion suite per store
20. `processor_aliases.json` for top-50 chips

---

## 15. Environment & Dependencies

### pyproject.toml (key dependencies)

```toml
[tool.poetry.dependencies]
python = "^3.11"

# Core scraping
scrapy = "^2.11"
scrapy-playwright = "^0.0.33"
scrapy-redis = "^0.7"
scrapy-rotating-proxies = "^0.6"
scrapy-useragents = "^0.0.1"
playwright-stealth = "^1.0"
fake-useragent = "^1.4"

# Validation
pydantic = "^2.5"
pydantic-settings = "^2.1"

# Database
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.29"
alembic = "^1.13"

# Task queue
celery = {extras = ["redis"], version = "^5.3"}
redis = "^5.0"

# Text extraction
flashtext = "^2.7"
spacy = "^3.7"                # optional NLP

# Images
rembg = "^2.0"
open-clip-torch = "^2.24"
imagehash = "^4.3"
Pillow = "^10.0"

# LLM fallback
anthropic = "^0.23"

# Monitoring
sentry-sdk = {extras = ["celery"], version = "^1.40"}
```

### Environment variables (pydantic-settings)

```python
# config/settings.py
class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/uz_scraper"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM (optional — only for fallback extraction)
    ANTHROPIC_API_KEY: str = ""
    LLM_EXTRACTION_ENABLED: bool = False
    LLM_CACHE_TTL_DAYS: int = 30        # cache results to avoid re-calling

    # Images
    IMAGES_STORE: str = "./data/images"
    REMBG_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_IMAGES_PER_PRODUCT: int = 5

    # Proxies
    PROXY_LIST_PATH: str = ""           # empty = no proxy rotation

    # Monitoring
    SENTRY_DSN: str = ""

    # Extraction thresholds
    SPEC_SCORE_STRUCTURED: float = 0.7
    SPEC_SCORE_REGEX: float = 0.4

    class Config:
        env_file = ".env"
```

### docker-compose.yml

```yaml
version: '3.9'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: uz_scraper
      POSTGRES_USER: scraper
      POSTGRES_PASSWORD: scraper
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  scraper:
    build: .
    depends_on: [postgres, redis]
    volumes:
      - ./data:/app/data
    env_file: .env
    command: celery -A tasks.celery_app worker --loglevel=info

  beat:
    build: .
    depends_on: [redis]
    env_file: .env
    command: celery -A tasks.celery_app beat --loglevel=info

volumes:
  pgdata:
```

### First-time setup

```bash
# Install dependencies
poetry install

# Install Playwright browsers
playwright install chromium

# Download spaCy Russian model (optional)
python -m spacy download ru_core_news_sm

# Run migrations
alembic upgrade head

# Run a single spider manually (for testing)
scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=10

# Start worker + beat
docker-compose up -d
```

---

## Key Design Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Spider engine | Scrapy (not Crawlee/Playwright standalone) | Pipelines, middlewares, dedup, stats are all built-in |
| Domain model | ProductFamily + ProductVariant split | Handles variants correctly without duplicates |
| Spec extraction | 3-strategy cascade | Avoids expensive LLM calls when structured data exists |
| Spec validation | Pydantic per category | Catches RAM/storage swaps and unit errors at boundary |
| Price storage | Append-only `price_records` | Full history preserved; easy to detect anomalies |
| Image quality | CLIP zero-shot classification | No training data needed; robust to new store layouts |
| Anti-bot | AutoThrottle + adaptive delay | Soft rate limiting (no 429) is the common UZ pattern |
| Canary tests | Hourly assertions on known products | Detect redesigns before full crawl fails silently |
| LLM extraction | Opt-in fallback with caching | Cost control; only for Uzum-style unstructured descriptions |
