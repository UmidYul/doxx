# UZ Tech Scraper — Project Documentation

> Полная документация для Cursor AI.
> Парсер — независимый сервис-сенсор. Собирает данные, нормализует,
> отправляет ТОЛЬКО изменения в CRM через REST API.
> CRM — главный. У него основная БД. Парсер про неё ничего не знает.

---

## 1. Роль парсера в системе

```
[Сайты магазинов]
      ↓ scrape
[Парсер]  →  parse_cache (своя БД)
      ↓ POST /api/parser/sync  (только дельта)
[CRM API]  →  основная БД CRM
      ↓ GET /api/products
[Сайт-каталог]
```

### Что парсер ДЕЛАЕТ
- Скрапит товары с 5 магазинов Узбекистана
- Нормализует сырые данные ДО отправки в CRM
- Сравнивает с parse_cache и шлёт ТОЛЬКО изменения
- Хранит сырые данные в собственных таблицах

### Что парсер НЕ ДЕЛАЕТ
- НЕ хранит полные карточки товаров долгосрочно
- НЕ занимается историей цен (это CRM)
- НЕ знает про структуру БД CRM
- НЕ показывает данные пользователям
- НЕ принимает решения о публикации товаров

---

## 2. Tech Stack

### Core
| Компонент       | Библиотека                  | Зачем                                      |
|-----------------|-----------------------------|--------------------------------------------|
| Spider engine   | `scrapy`                    | Очередь, retry, rate limit из коробки      |
| JS рендеринг    | `scrapy-playwright`         | Для React SPA (uzum.uz)                    |
| Валидация       | `pydantic v2`               | Нормализованные модели событий             |
| БД парсера      | `supabase-py` + hosted Postgres | parse_cache, очереди, логи (без Storage)   |
| Синхронный SQL  | `psycopg2-binary`           | Прямое подключение для Scrapy / скриптов   |
| Миграции        | `alembic`                   | Версионирование схемы                      |
| Шедулер         | `celery` + `celery-beat`    | Три ритма парсинга                         |
| Очередь задач   | `redis`                     | Broker для Celery + bloom filter           |
| HTTP клиент     | `httpx`                     | Отправка событий в CRM API                 |

### Извлечение данных
| Компонент         | Библиотека      | Зачем                                |
|-------------------|-----------------|--------------------------------------|
| Быстрый поиск     | `flashtext`     | Keyword matching для нормализации    |
| HTML парсинг      | `parsel`        | XPath + CSS (встроен в Scrapy)       |
| Изображения       | `rembg`         | Убрать фон с баннеров                |
| Классификация фото| `open_clip`     | CLIP: clean shot vs banner           |
| Хеш изображений   | `imagehash`     | Дедупликация по phash                |
| LLM fallback      | `anthropic`     | Только для неструктурированных specs |

### Инфраструктура
| Компонент       | Инструмент                  |
|-----------------|-----------------------------|
| Прокси ротация  | `scrapy-rotating-proxies`   |
| Anti-bot        | `playwright-stealth`        |
| User-agent      | `fake-useragent`            |
| Мониторинг      | `sentry-sdk`                |
| Конфиг          | `pydantic-settings`         |

---

## 3. Структура проекта

```
uz_tech_scraper/
│
├── domain/                        # Модели данных парсера
│   ├── events.py                  # ProductFound, PriceChanged, OutOfStock, CharAdded
│   ├── normalized_product.py      # NormalizedProduct — что шлём в CRM
│   ├── raw_product.py             # RawProduct — что достал спайдер
│   └── specs/                     # Нормализованные схемы характеристик
│       ├── base.py                # BaseSpecs + completeness_score
│       ├── phone.py               # PhoneSpecs
│       ├── laptop.py              # LaptopSpecs
│       ├── tv.py                  # TVSpecs
│       └── appliance.py           # ApplianceSpecs
│
├── application/                   # Бизнес-логика парсера
│   ├── parse_orchestrator.py      # fast_parse / full_parse / discover
│   ├── delta_detector.py          # Сравнение с parse_cache → дельта
│   ├── crm_client.py              # HTTP клиент для CRM API
│   ├── event_sender.py            # Отправка + retry через pending_events
│   └── extractors/
│       ├── spec_extractor.py      # Каскад: structured → regex → LLM
│       ├── structured_extractor.py
│       ├── regex_extractor.py
│       ├── llm_extractor.py
│       ├── unit_normalizer.py
│       ├── image_extractor.py
│       └── patterns.py            # Regex паттерны RU + UZ
│
├── infrastructure/
│   ├── spiders/
│   │   ├── base.py                # BaseProductSpider (abstract)
│   │   ├── mediapark.py
│   │   ├── olx.py
│   │   ├── texnomart.py
│   │   ├── makro.py
│   │   └── uzum.py                # GraphQL interceptor
│   ├── pipelines/
│   │   ├── validate_pipeline.py   # Проверка обязательных полей
│   │   ├── normalize_pipeline.py  # RawProduct → NormalizedProduct
│   │   ├── image_pipeline.py      # В память: CLIP + rembg → image_urls_ranked (URL магазина)
│   │   └── delta_pipeline.py      # Сравнение с cache → событие → очередь
│   ├── middlewares/
│   │   ├── ratelimit_middleware.py
│   │   ├── stealth_middleware.py
│   │   ├── retry_middleware.py
│   │   └── mobile_redirect_middleware.py
│   └── db/
│       ├── supabase_client.py     # Singleton Supabase client
│       ├── parse_cache_repo.py    # parse_cache через Supabase
│       ├── event_repo.py          # pending_events через Supabase
│       ├── store_repo.py          # Сырые таблицы магазинов (upsert)
│       ├── records.py             # ParseCacheRecord / PendingEventRecord
│       ├── session.py             # psycopg2 для прямого SQL (опционально)
│       └── migrations/            # Alembic → тот же Postgres (Supabase)
│
├── config/
│   ├── settings.py                # pydantic-settings
│   ├── scrapy_settings.py
│   └── processor_aliases.json    # SM8550 → Snapdragon 8 Gen 2
│
├── tasks/
│   ├── celery_app.py             # Beat schedule: 3 ритма
│   ├── parse_tasks.py            # fast_parse / full_parse / discover
│   └── event_tasks.py            # retry pending_events
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── canary/                   # Canary assertions per store
│
├── .cursor/mcp.json
├── .cursorrules
├── docker-compose.yml
├── pyproject.toml
└── alembic.ini
```

---

## 4. База данных парсера

Парсер владеет ТОЛЬКО своими таблицами. В БД CRM не ходит никогда.

Таблицы живут в **Supabase** (hosted PostgreSQL). Схема накатывается **Alembic** с локальной машины или CI: `DATABASE_URL_SYNC` / `SUPABASE_DB_URL` — строка подключения из Supabase Dashboard → Settings → Database → Connection string (URI). После `alembic upgrade head` один раз выполни `migrations/versions/002_supabase_functions.sql` в SQL Editor (функция `increment_retry` для атомарного retry). **Supabase Storage не используется** — изображения не сохраняются в парсере; в CRM уходят только URL с сайта магазина (`image_urls` / `image_urls_ranked`). В Table Editor удобно смотреть `parse_cache` и `pending_events` при отладке.

Прикладной код не использует SQLAlchemy ORM: чтение/запись идут через **supabase-py** (`get_supabase()`), опционально — прямой **psycopg2** из `infrastructure/db/session.py`.

### Таблицы магазинов (сырые данные)

```sql
-- По одной таблице на каждый магазин
CREATE TABLE mediapark_products (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    price       NUMERIC(15,2),
    in_stock    BOOLEAN DEFAULT true,
    url         TEXT UNIQUE NOT NULL,
    characteristics JSONB DEFAULT '{}',
    images      TEXT[],
    parsed_at   TIMESTAMPTZ DEFAULT now(),
    raw_html    TEXT           -- для отладки, можно TTL
);

CREATE TABLE olx_products        (LIKE mediapark_products INCLUDING ALL);
CREATE TABLE texnomart_products  (LIKE mediapark_products INCLUDING ALL);
CREATE TABLE makro_products      (LIKE mediapark_products INCLUDING ALL);
CREATE TABLE uzum_products       (LIKE mediapark_products INCLUDING ALL);
```

### parse_cache — главная таблица сравнения

```sql
CREATE TABLE parse_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT UNIQUE NOT NULL,
    source_name     TEXT NOT NULL,       -- 'mediapark', 'uzum', ...
    source_id       TEXT,                -- id в таблице магазина
    last_price      NUMERIC(15,2),
    last_in_stock   BOOLEAN,
    last_parsed_at  TIMESTAMPTZ,
    crm_listing_id  UUID,               -- ID листинга в CRM
    crm_product_id  UUID,               -- ID товара в каталоге CRM
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cache_source ON parse_cache(source_name, source_id);
CREATE INDEX idx_cache_url    ON parse_cache(url);
```

### parse_logs

```sql
CREATE TABLE parse_logs (
    id           SERIAL PRIMARY KEY,
    source_name  TEXT NOT NULL,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    items_parsed INT DEFAULT 0,
    items_changed INT DEFAULT 0,
    items_new    INT DEFAULT 0,
    errors       JSONB DEFAULT '[]',
    status       TEXT DEFAULT 'running'  -- running/done/failed
);
```

### parse_queue

```sql
CREATE TABLE parse_queue (
    id           SERIAL PRIMARY KEY,
    source_name  TEXT NOT NULL,
    url          TEXT NOT NULL,
    priority     INT DEFAULT 5,
    scheduled_at TIMESTAMPTZ DEFAULT now(),
    attempts     INT DEFAULT 0,
    last_error   TEXT,
    status       TEXT DEFAULT 'pending'  -- pending/processing/done/failed
);

CREATE INDEX idx_queue_schedule ON parse_queue(status, scheduled_at);
```

### pending_events — отказоустойчивость

```sql
CREATE TABLE pending_events (
    id          SERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,           -- product_found/price_changed/...
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    retry_count INT DEFAULT 0,
    last_error  TEXT,
    status      TEXT DEFAULT 'pending'   -- pending/sent/failed
);
```

---

## 5. Алгоритм парсинга (пошагово)

```
1. Взять задачу из parse_queue

2. Загрузить страницу товара (Scrapy + Playwright если нужен JS)

3. Извлечь сырые данные: name, price, in_stock, specs{}, images[]

4. Нормализовать (парсер делает сам до отправки в CRM):
   - Specs: каскад structured → regex → LLM
   - Цена: "2 990 000 сум" → Decimal(2990000)
   - Бренд: "эпл" → "Apple"
   - Единицы: "256гб" → {value: 256, unit: "GB"}

5. Сохранить в таблицу магазина (mediapark_products и т.д.)

6. Проверить parse_cache по URL:

   ЕСТЬ в кэше:
     Сравнить price / in_stock с last_price / last_in_stock
     Изменилось → создать событие price_changed / out_of_stock
     Не изменилось → ничего (это и есть "только дельта")
     Новая характеристика → событие characteristic_added

   НЕТ в кэше (новый товар):
     GET /api/parser/catalog/find → CRM ищет совпадение
     Создать событие product_found (с crm_product_id или без)
     Сохранить crm_listing_id + crm_product_id из ответа CRM

7. Добавить событие в pending_events
8. event_sender отправляет пачками (batch до 100) в CRM API
9. При успехе: обновить parse_cache, пометить pending_events как sent
10. Записать результат в parse_logs
```

---

## 6. Три ритма парсинга

```python
# tasks/celery_app.py

app.conf.beat_schedule = {
    # Цены и наличие — часто
    'fast-parse-all': {
        'task': 'tasks.parse_tasks.fast_parse_all',
        'schedule': crontab(minute=0, hour='*/2'),  # каждые 2 часа
    },
    # Характеристики — редко (дорого, JS рендеринг)
    'full-parse-all': {
        'task': 'tasks.parse_tasks.full_parse_all',
        'schedule': crontab(hour=0, day_of_week=0),  # раз в неделю
    },
    # Поиск новых товаров
    'discover-all': {
        'task': 'tasks.parse_tasks.discover_all',
        'schedule': crontab(hour=3, minute=0),  # раз в день в 3:00
    },
    # Retry pending_events
    'retry-events': {
        'task': 'tasks.event_tasks.retry_pending',
        'schedule': crontab(minute='*/5'),  # каждые 5 минут
    },
}
```

### Что делает каждый режим

`fast_parse()` — только price + in_stock. Не загружает детальную страницу
если не нужно. Для статических магазинов берёт данные из листинга.

`full_parse()` — полная загрузка карточки товара. Specs, фото, описание.
Запускается для товаров у которых `last_full_parse_at` > 7 дней назад.

`discover()` — обходит категории в поисках новых URL которых нет в
parse_cache. Добавляет их в parse_queue.

---

## 7. API взаимодействие с CRM

```python
# application/crm_client.py

CRM_BASE_URL  = settings.CRM_API_URL         # http://crm-service/api
CRM_API_KEY   = settings.CRM_API_KEY         # секретный ключ

HEADERS = {
    "X-Parser-Key": CRM_API_KEY,
    "Content-Type": "application/json",
}

# Эндпоинты
POST  /api/parser/sync         # одно событие
POST  /api/parser/sync/batch   # до 100 событий
GET   /api/parser/catalog/find # найти товар по source + source_id
```

### Форматы событий

```python
# domain/events.py

class ProductFoundEvent(BaseModel):
    event: Literal["product_found"] = "product_found"
    source: str                    # "mediapark"
    source_url: str
    source_id: str
    crm_product_id: Optional[UUID] = None  # если CRM уже нашёл совпадение
    product: ProductPayload
    listing: ListingPayload

class PriceChangedEvent(BaseModel):
    event: Literal["price_changed"] = "price_changed"
    crm_listing_id: UUID           # из parse_cache
    listing: ListingPayload        # новая цена

class OutOfStockEvent(BaseModel):
    event: Literal["out_of_stock"] = "out_of_stock"
    crm_listing_id: UUID
    parsed_at: datetime

class CharacteristicAddedEvent(BaseModel):
    event: Literal["characteristic_added"] = "characteristic_added"
    crm_product_id: UUID
    characteristics: dict          # только новые / исправленные поля

# Ответ CRM
class CRMSyncResponse(BaseModel):
    status: Literal["ok", "error"]
    crm_listing_id: Optional[UUID]
    crm_product_id: Optional[UUID]
    action: Literal["created", "matched", "needs_review"]
```

### Отказоустойчивость

CRM недоступен → событие сохраняется в `pending_events` → Celery
retry каждые 5 минут. Максимум 10 попыток, потом `status='failed'`
и алерт в Sentry.

```python
# application/event_sender.py

async def send_event(event: BaseEvent) -> bool:
    try:
        response = await crm_client.post("/api/parser/sync", event)
        if response.status_code == 200:
            return True
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    # Сохранить в pending_events для retry
    await event_repo.save_pending(event)
    return False
```

---

## 8. Нормализация (парсер делает до отправки в CRM)

### Иерархия источников

```python
METHOD_PRIORITY = {
    "structured": 3,  # таблица характеристик на сайте
    "regex":      2,  # найдено в описании
    "llm":        1,  # LLM извлечение
    "unknown":    0,
}
```

### Правила нормализации

```python
# Единицы измерения
"256гб" / "256 Гб" / "256ГБ"      → storage_gb: 256
"6.1 дюйм" / "6,1 inch"            → display_size_inch: 6.1
"5000мАч" / "5000 mAh"             → battery_mah: 5000

# Бренды
"эпл" / "apple" / "APPLE"          → brand: "Apple"
"самсунг" / "samsung"               → brand: "Samsung"
"сяоми" / "xiaomi" / "Xiaomi"      → brand: "Xiaomi"

# Процессоры (aliases)
"SM8550" / "SM8550-AB"              → processor: "Snapdragon 8 Gen 2"

# Цвета
"черный титан" / "Black Titanium"   → color: "Black Titanium"
"синий" / "blue" / "ko'k"          → color: "Blue"

# Цены (UZS)
"2 990 000 сум" / "2,990,000"      → Decimal(2990000)
"По договорённости" / "Narxi: ..."  → PriceStatus.ON_REQUEST
```

### Каскад извлечения specs

```
1. StructuredExtractor  — таблица характеристик (Mediapark, Texnomart)
   completeness_score >= 0.7 → стоп

2. RegexExtractor       — паттерны по описанию (OLX, частично Uzum)
   completeness_score >= 0.4 → стоп

3. LLMExtractor         — Claude Haiku, только если score < 0.4
   Результат кешируется по sha256(text) на 30 дней
```

### Конфликты между магазинами

Правило: если хотя бы один источник дал характеристику и она
прошла валидацию — включаем. Отсутствие у другого магазина игнорируем.

Приоритет при конфликте значений: structured > regex > llm.

---

## 9. Спайдеры

### BaseProductSpider

```python
# Все спайдеры наследуют от него
class BaseProductSpider(scrapy.Spider):
    store_name: str = ""

    # Три режима — переопределить нужные
    def fast_parse_item(self, response) -> dict:
        """Только price + in_stock. Быстро, без деталей."""
        raise NotImplementedError

    def full_parse_item(self, response) -> dict:
        """Полная карточка: specs, images, description."""
        raise NotImplementedError

    def discover_urls(self, response) -> list[str]:
        """Новые URL из листинга категории."""
        raise NotImplementedError

    # Общие защиты
    def _zero_result_guard(self, urls, response):
        if not urls and response.meta.get('page', 1) == 1:
            self.logger.warning(f"[ZERO_RESULT] {response.url}")

    def _infinite_pagination_guard(self, next_url) -> bool:
        # Bloom filter check на хеш первых 5 товаров страницы
        ...
```

### Магазины и их особенности

| Магазин     | Рендеринг    | Specs          | Пагинация       |
|-------------|--------------|----------------|-----------------|
| mediapark   | HTML static  | таблица (RU)   | ?page=N         |
| olx         | HTML static  | описание       | ?page=N         |
| texnomart   | mixed JS     | таблица RU+UZ  | ?page=N         |
| makro       | REST API     | JSON array     | cursor/offset   |
| uzum        | React SPA    | GraphQL + desc | cursor          |

**Uzum (GraphQL interceptor):**
```python
# Перехватываем сетевые ответы вместо DOM парсинга
page.on('response', lambda r: capture_if_graphql(r))
# payload: data.makeSearch.items[].catalogItem
```

---

## 10. Обработка ошибок

| Ситуация                     | Действие                                       |
|------------------------------|------------------------------------------------|
| Сайт недоступен              | retry через 30 мин, до 3 попыток, лог          |
| Товар удалён с сайта         | `out_of_stock` в CRM, убрать из queue          |
| CRM недоступен               | сохранить в `pending_events`, retry каждые 5 мин |
| Структура сайта изменилась   | critical лог, алерт Sentry, остановить источник |
| 200 + пустой body            | soft block — IgnoreRequest, увеличить delay    |
| Redirect на мобильную версию | retry с desktop User-Agent                     |
| Бесконечная пагинация        | bloom filter на хеш первых 5 товаров           |
| RAM > 32 GB в phone          | sanity swap: это storage, не RAM               |

---

## 11. Anti-detection

```python
# config/scrapy_settings.py

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
DOWNLOAD_DELAY = 1.5

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--disable-blink-features=AutomationControlled"],
}

DOWNLOADER_MIDDLEWARES = {
    'infrastructure.middlewares.stealth_middleware.StealthMiddleware':    400,
    'scrapy_rotating_proxies.middlewares.RotatingProxyMiddleware':        610,
    'infrastructure.middlewares.ratelimit_middleware.AdaptiveRateLimit':  700,
}
```

**AdaptiveRateLimitMiddleware:** отслеживает `response_time` за последние
10 запросов. Если текущее время > 3x от медианы → увеличить DOWNLOAD_DELAY
на 1.5x. Лог `[RATE_LIMIT_SUSPECTED]`.

---

## 12. Canary система

Ежечасная проверка что конкретный товар-маяк парсится корректно.

```python
CANARY_PRODUCTS = {
    "mediapark": {
        "url": "https://mediapark.uz/...",
        "assertions": {
            "brand": "Samsung",
            "specs.ram_gb": 8,
            "price": lambda v: 5_000_000 < v < 25_000_000,
        }
    },
    # для каждого магазина
}
```

При провале: лог `[CANARY_FAIL]` + алерт в Sentry.

---

## 13. Environment variables

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...   # service_role — запись в таблицы через supabase-py (не anon)
SUPABASE_DB_URL=postgresql://postgres:[password]@db.xxx.supabase.co:5432/postgres
DATABASE_URL_SYNC=            # опционально; если пусто — берётся из SUPABASE_DB_URL (Alembic / psycopg2)

# Redis
REDIS_URL=redis://localhost:6379/0

# CRM API
CRM_API_URL=http://crm-service/api
CRM_API_KEY=secret-parser-key

# LLM (опционально)
ANTHROPIC_API_KEY=
LLM_EXTRACTION_ENABLED=false
LLM_CACHE_TTL_DAYS=30

# Изображения (классификация в памяти; файлы не сохраняются, в CRM — только URL)
REMBG_CONFIDENCE_THRESHOLD=0.7
MAX_IMAGES_PER_PRODUCT=5

# Прокси (опционально)
PROXY_LIST_PATH=

# Мониторинг
SENTRY_DSN=

# Пороги
SPEC_SCORE_THRESHOLD_STRUCTURED=0.7
SPEC_SCORE_THRESHOLD_REGEX=0.4
```

---

## 14. Ключевые инварианты — никогда не нарушать

- Парсер НИКОГДА не обращается к БД CRM напрямую
- Парсер НИКОГДА не отправляет событие если price и in_stock не изменились
- `parse_cache` обновляется ТОЛЬКО после успешного ответа от CRM
- `pending_events` — единственный способ гарантировать доставку при сбоях
- Нормализация ВСЕГДА происходит до отправки в CRM (CRM получает чистые данные)
- `raw_html` сохраняется для отладки, но не является источником истины

---

## 15. Supabase setup

1. Создай проект на [supabase.com](https://supabase.com).
2. **Settings → API**: скопируй **Project URL** → `SUPABASE_URL`, **service_role** key → `SUPABASE_SERVICE_KEY` (только сервер/CI; anon key для парсера не подходит).
3. **Settings → Database → Connection string (URI)** → `SUPABASE_DB_URL` (и при необходимости `DATABASE_URL_SYNC` для Alembic; если пусто — в коде подставляется из `SUPABASE_DB_URL`).
4. Локально или в CI: `alembic upgrade head` — создаёт все таблицы парсера в том же Postgres.
5. В **SQL Editor** один раз выполни `migrations/versions/002_supabase_functions.sql` (или `python scripts/apply_supabase_functions.py`) — функция `increment_retry(event_id, err)` для атомарного увеличения `retry_count` в `pending_events`.

**Важно:** **Supabase Storage не используется.** Парсер не хранит изображения ни локально, ни в облаке: `ImageClassifierPipeline` качает байты в память, прогоняет CLIP/rembg при необходимости и отбрасывает файл; в событиях для CRM остаются **исходные URL магазина** (`image_urls_ranked` / `image_urls`). Загрузку и хранение картинок делает CRM.

### Отладка данных

- **Table Editor**: `parse_cache`, `pending_events`, `mediapark_products` и т.д.
- Логи: тег `[SUPABASE_ERROR]` при ошибках PostgREST/Supabase client.

### Python

Рекомендуется **Python 3.11–3.13**. На **3.14** часть зависимостей может тянуть пакеты без готовых колёс под Windows. В `pyproject.toml` при необходимости задана верхняя граница `<3.14`.
