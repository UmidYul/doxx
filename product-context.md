# IMPORTANT FOR AI

This document is HIGH-LEVEL product context.

DO NOT:
- change MVP scope based on this file
- invent new features outside MVP
- override ai-context.md or mvp-context.md

USE THIS FILE ONLY FOR:
- understanding business goals
- naming decisions
- prioritization

# AI PRIORITY ORDER
1. .cursorrules (STRICT RULES)
2. ai-context.md (MVP guardrails)
3. mvp-context.md (MVP scope)
4. project-context.md (architecture summary)
5. product-context.md (deep reference)
6. deep-research-report.md (plan)

IMPORTANT:
This file may contain research artifacts (e.g., tool citation markers).
Remove/ignore tokens like "cite..." when using this file for development.

# MVP‑ready техническое ТЗ для E‑каталога с агрегацией предложений и инжестом данных

## Executive summary

Ваш исходный текст задаёт правильную рамку (агрегация предложений, сравнение цен, продавцы, очереди, монорепо), но в текущем виде это не исполнимое ТЗ: нет чёткой доменной модели, схемы данных, API‑контракта, pipeline инжеста и эксплуатационных SLO/SLA. Для E‑каталога это критично, потому что продуктовая ценность строится на качестве данных (freshness/coverage), поиске и SEO‑индексации, а не просто на выборе фреймворков. 

Ниже — спецификация “MVP‑ready” под разработку в Cursor: структура монорепо (папки/файлы/назначение), доменные сущности и Postgres‑схема с индексами, pipeline инжеста (feeds/sitemaps/scraping) на BullMQ c retry/backoff/rate limiting и snapshotting цен, дедупликация GTIN→правила→ручная модерация, полный REST‑контракт (плюс опциональный GraphQL), Next.js App Router структура с SSR/SSG/ISR для SEO, DevOps (Docker/Compose/CI/CD/деплой Railway/Render/секреты/миграции Prisma), observability (OpenTelemetry), безопасность/комплаенс (RFC9309 robots, takedown/DMCA‑style процесс, PII, WAF), тесты и roadmap с P0/P1/P2. 

## Проблемные зоны исходного описания и улучшения

Главная слабость исходного текста — смешение трёх разных продуктов в одном “MVP”: агрегатор/сравнение цен (traffic+SEO+кликаут), маркетплейс (платежи/возвраты/фрод/поддержка) и CRM (B2B‑продажи+интеграции). Это резко увеличивает объём требований по данным, безопасности и операции, причём эти требования не описаны (например, контур транзакций, антифрод, финансовая отчётность) — значит проект рискует застрять в бесконечной “архитектуре” без релиза. В MVP‑логике целесообразно зафиксировать ядро: “каталог + предложения + сравнение + кликаут + удержание (избранное/алерты)”, а marketplace/CRM вынести в Scale‑фазу. 

Вторая слабость — упоминание DDD и “системной архитектуры” без реального содержания. Для каталога это означает отсутствие ответа на вопросы: что является “каноническим товаром”, что такое “предложение”, как хранить цену во времени, как мерить свежесть данных, как матчить одинаковые товары у разных источников. Все эти сущности должны быть первыми артефактами (ER + таблицы + индексы), иначе вы неизбежно получите “дрейф” данных, а затем дорогостоящий рефакторинг. 

Третья слабость — ранний оверкилл инфраструктуры, особенно если с первого дня добавлять отдельный поисковый кластер. В MVP лучше использовать возможности Postgres полнотекстового поиска: `tsvector/tsquery` + GIN/GiST индексы для регулярных поисковых запросов, и расширение `pg_trgm` (опционально) для fuzzy‑search по названиям/моделям. Это даёт быстрый time‑to‑market и снижает DevOps‑нагрузку; отдельный поисковый движок подключается, когда вы действительно упираетесь в релевантность/нагрузку (значения порогов — не указано). 

Четвёртая слабость — “anti‑scraping” обсуждается через технику обхода, а не через комплаенс‑политику. Robots Exclusion Protocol по RFC9309 прямо указывает: правила robots — это запрос к соблюдению, и они **не являются формой авторизации доступа**, а также robots.txt **не является заменой** реальным мерам безопасности. Для коммерческого продукта критично иметь policy: какие пути разрешены, какие запрещены, как вы реагируете на takedown/жалобы, как минимизируете ущерб источнику (rate limiting/backoff) и как снижаете риск блокировок (feeds/sitemaps/партнёрства). 

## Структура монорепо и технологический стек

Ниже — структура, рассчитанная на быстрый старт команды в Cursor: единый репозиторий, общий пакет типов/DTO, единый пакет БД (Prisma schema + миграции), Next.js как UI + BFF API (Route Handlers), отдельный инжест‑воркер на BullMQ/Redis.

Ключевой инженерный принцип: “DB + shared types = контракт”, чтобы Cursor‑кодер/команда не изобретали разные версии сущностей в разных сервисах. Prisma Migrate предназначен для синхронизации схемы с БД и ведёт историю SQL‑миграций, а `prisma migrate deploy` рекомендуется включать в CI/CD для stage/prod. 

### Стек (MVP‑выборы и rationale)

ТАБЛИЦА A — Технологический стек/инструменты (plain text)

+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Слой                   | MVP-выбор                      | Зачем / обоснование                                         | Scale-опции / когда включать                 |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Web UI + BFF API       | Next.js App Router + Route     | Route Handlers в app/ поддерживают HTTP-методы; удобный      | Вынос отдельного API-сервиса (не указано:    |
|                        | Handlers                        | BFF-подход; единый деплой для MVP                            | Fastify/NestJS)                              |
|                        |                               | Route Handlers доступны только в app/ и эквивалентны API     |                                              |
|                        |                               | Routes из pages/                                            |                                              |
|                        |                               |                               |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Инжест (scraping)      | Playwright (Node)              | page.evaluate() выполняет JS в контексте страницы; network   | Максимальный сдвиг в сторону feeds/sitemaps  |
|                        |                               | interception через page.route()                              | (устойчивее и дешевле)                       |
|                        |                               |               |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Очереди / воркеры      | BullMQ + Redis                 | Retries/backoff, rate limiting, concurrency, job schedulers  | Разделение по доменам/категориям, multi-region|
|                        |                               | (v5.16+)                                                     | (не указано)                                 |
|                        |                               |   |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| База данных            | PostgreSQL                     | FTS: tsvector/tsquery + GIN/GiST; jsonb индексация;          | Партиционирование snapshot-таблиц            |
|                        |                               | pg_trgm для fuzzy                                            |                           |
|                        |                               |               |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| ORM/миграции           | Prisma ORM + Prisma Migrate    | Индексы/constraints в schema; migrate deploy в CI/CD         | Raw SQL для tsvector triggers и спец.индексов|
|                        |                               |               |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Observability          | OpenTelemetry + Collector +    | Collector — vendor-agnostic receive/process/export;          | Любой backend (Prometheus/Jaeger/вендор —    |
|                        | OTLP exporter                  | Node.js getting started + OTLP env vars                      | не указано)                                  |
|                        |                               |   |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| CI/CD                 | GitHub Actions                 | Workflows YAML; secrets; service containers Postgres/Redis   | Разделение пайплайнов по приложениям/окружения|
|                        |                               |   |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+
| Deploy (PaaS)          | Railway или Render             | Railway переменные как env vars; Render background workers   | Kubernetes — только при необходимости (не     |
|                        |                               | и cron jobs                                                   | указано)                                     |
|                        |                               |   |                                              |
+------------------------+-------------------------------+-------------------------------------------------------------+----------------------------------------------+

### Монорепо: файлы/папки/назначение

```text
e-catalog/
  apps/
    web/                                  # Next.js App Router: UI + BFF API
      app/
        (public)/                         # Публичные SEO маршруты
          page.tsx                        # /
          search/page.tsx                 # /search?q=
          c/[...slug]/page.tsx            # /c/<category-path>
          p/[slug]/page.tsx               # /p/<product-slug>
          brand/[slug]/page.tsx           # /brand/<slug>
          store/[slug]/page.tsx           # /store/<slug>
          sitemap.ts                      # sitemap.xml генерация (special)
          robots.txt/route.ts             # robots.txt как Route Handler (опционально)
        (account)/                        # Авторизованные страницы
          favorites/page.tsx
          alerts/page.tsx
        api/
          v1/
            health/route.ts
            search/route.ts
            categories/route.ts
            brands/route.ts
            products/route.ts
            products/[id]/route.ts
            products/[id]/offers/route.ts
            offers/[id]/redirect/route.ts
            stores/route.ts
            stores/[slug]/route.ts
            me/route.ts
            favorites/route.ts
            alerts/route.ts
            admin/
              ingest/route.ts
              moderation/route.ts
      src/
        components/
          layout/
          search/
          product/
        lib/
          db.ts                            # Prisma client singleton
          auth.ts                          # adapter (вариант auth — не указано)
          rbac.ts                          # роли USER/SELLER/ADMIN
          rate-limit.ts                    # лимитер (реализация — не указано)
          seo.ts                           # генерация canonical/metadata
        instrumentation.ts                 # серверная observability init (опц.)
        instrumentation-client.ts          # клиентская observability init (опц.)
      next.config.ts
      package.json

  services/
    ingest/                               # BullMQ workers + connectors
      src/
        index.ts
        config.ts                          # env schema (zod) + загрузка
        queues/
          connection.ts                    # Redis connection
          names.ts
          producers.ts                      # job schedulers и enqueue
        workers/
          fetch-list.worker.ts              # feed/sitemap -> URL list
          fetch-page.worker.ts              # playwright fetch
          parse-offer.worker.ts             # extraction + normalization
          upsert-offer.worker.ts            # DB upsert + snapshot insertion
          match-product.worker.ts           # GTIN -> rules -> moderation
          alerts-evaluate.worker.ts         # price alerts
        connectors/
          feed/
            csv.ts
            xml.ts
          sitemap/
            sitemap.ts
          scrape/
            playwright.ts
            extractors/
              generic-dom.ts
              jsonld.ts                     # если источник отдаёт JSON-LD (опционально)
        domain/
          normalize.ts                      # price/currency/title normalization
          gtin.ts                           # GTIN validation/check digit (опц.)
          matching.ts                       # rules-based matching
        telemetry/
          otel.ts                           # OpenTelemetry init
      Dockerfile
      package.json

  packages/
    shared/
      src/
        dto/                               # API DTO types
        domain/                            # domain types (Product/Offer/etc.)
        validation/                        # zod schemas for DTO
        constants/                         # enums: roles, availability, match types
    db/
      prisma/
        schema.prisma
        migrations/
      src/
        client.ts                          # Prisma client export

  tools/
    mcp/
      catalog-devtools/                    # локальный MCP server (наши tools)
        src/
          server.ts
          tools/
            db.ts
            ingest.ts
            queues.ts
        package.json
      scripts/
        run-with-env.sh                    # wrapper для env (если нужно)
    docs/
      architecture.md
      api.md

  infra/
    docker/
      compose.yaml
      web.Dockerfile
      otel-collector.yaml
    ci/
      env.example
  .github/workflows/
    ci.yaml
    deploy.yaml

  .cursor/
    mcp.example.json                       # пример MCP конфиг (без секретов)
  .gitignore
  README.md
```

Почему `sitemap.ts` и Route Handlers именно так: Next.js документирует `sitemap.(js|ts)` как “special file” для генерации sitemap, а Route Handlers — как специальный файл `route.js|ts`, поддерживающий стандартные HTTP‑методы в App Router. 

Почему отдельный сервис `services/ingest`: BullMQ позиционируется как очередь с воркерами для выполнения фоновых задач, а job schedulers (v5.16+) предназначены для repeatable задач (по cron/interval), что идеально ложится на регулярное обновление цен и обход источников. 

## Доменная модель и Postgres схема

### ER‑диаграмма (mermaid)

```mermaid
erDiagram
  CATEGORY ||--o{ CATEGORY : parent
  BRAND ||--o{ PRODUCT : owns
  CATEGORY ||--o{ PRODUCT : classifies

  PRODUCT ||--o{ PRODUCT_GTIN : has
  PRODUCT ||--o{ OFFER_MATCH : matched_by
  PRODUCT ||--o{ FAVORITE : saved_by
  PRODUCT ||--o{ PRICE_ALERT : watched_by

  PROVIDER ||--o{ OFFER : publishes
  OFFER ||--o{ PRICE_SNAPSHOT : snapshots
  OFFER ||--o{ OFFER_MATCH : matches
  OFFER ||--o{ CLICKOUT_EVENT : clickouts

  SOURCE_CONFIG ||--o{ INGEST_JOB : scheduled
  INGEST_JOB ||--o{ INGEST_RUN : runs
  INGEST_RUN ||--o{ RAW_PAYLOAD : captures

  USER_IDENTITY ||--o{ USER_ROLE : has
  USER_IDENTITY ||--o{ FAVORITE : creates
  USER_IDENTITY ||--o{ PRICE_ALERT : creates

  CATEGORY {
    uuid id PK
    uuid parent_id FK
    text name
    text slug
  }

  BRAND {
    uuid id PK
    text name
    text slug
  }

  PRODUCT {
    uuid id PK
    uuid category_id FK
    uuid brand_id FK
    text title
    text slug
    jsonb attributes
    tsvector search_vector
  }

  PRODUCT_GTIN {
    uuid product_id FK
    text gtin
    text gtin_type
  }

  PROVIDER {
    uuid id PK
    text type
    text name
    text slug
    text website_url
  }

  OFFER {
    uuid id PK
    uuid provider_id FK
    uuid product_id FK
    text external_id
    text url
    text title
    text gtin
    text currency
    bigint price_minor
    text availability
    timestamptz last_seen_at
  }

  PRICE_SNAPSHOT {
    uuid id PK
    uuid offer_id FK
    timestamptz captured_at
    text currency
    bigint price_minor
    text availability
  }

  OFFER_MATCH {
    uuid offer_id FK
    uuid product_id FK
    text match_type
    numeric confidence
    uuid decided_by_user_id
    timestamptz decided_at
  }

  USER_IDENTITY {
    uuid id PK
    text auth_provider
    text provider_user_id
    text email
    text phone
  }

  USER_ROLE {
    uuid user_id FK
    text role
  }

  FAVORITE {
    uuid user_id FK
    uuid product_id FK
  }

  PRICE_ALERT {
    uuid id PK
    uuid user_id FK
    uuid product_id FK
    bigint target_price_minor
    text currency
    boolean is_active
  }

  SOURCE_CONFIG {
    uuid id PK
    text name
    text base_url
    text mode
    jsonb config
    int requests_per_minute
    boolean robots_respected
  }

  INGEST_JOB {
    uuid id PK
    uuid source_config_id FK
    text schedule_type
    text schedule_value
    boolean is_active
  }

  INGEST_RUN {
    uuid id PK
    uuid ingest_job_id FK
    text status
    int offers_upserted
    int errors_count
    timestamptz started_at
    timestamptz finished_at
  }

  RAW_PAYLOAD {
    uuid id PK
    uuid ingest_run_id FK
    text kind
    text url
    jsonb payload
  }

  CLICKOUT_EVENT {
    uuid id PK
    uuid offer_id FK
    uuid user_id FK
    text session_id
    inet ip
    text user_agent
  }
```

### Postgres: ключевые таблицы, поля и индексы (MVP)

Ниже — минимальный набор таблиц. Поля, содержащие персональные данные (PII), отмечены. Политика retention по PII и raw payloads — **не указано** и должна быть утверждена до production‑запуска.

Ключ по поиску: `product.search_vector` (tsvector) + GIN индекс. Postgres документирует GIN/GiST как предпочтительные типы индексов для ускорения полнотекстового поиска, и приводит пример `CREATE INDEX ... USING GIN(tsvector_column)`. 

Ключ по фильтрам: `product.attributes` (jsonb) + GIN индекс. Postgres документирует `jsonb` indexing и указывает, что GIN индексы можно использовать для эффективного поиска ключей/пар ключ‑значение в `jsonb`. 

plain text (схема/индексы):

1) category
- id uuid PK
- parent_id uuid FK -> category.id NULL
- name text NOT NULL
- slug text NOT NULL UNIQUE
- created_at timestamptz NOT NULL DEFAULT now()
Indexes:
- uq_category_slug(slug)
- idx_category_parent(parent_id)

2) brand
- id uuid PK
- name text NOT NULL
- slug text NOT NULL UNIQUE
Indexes:
- uq_brand_slug(slug)

3) product
- id uuid PK
- category_id uuid FK NOT NULL
- brand_id uuid FK NULL
- title text NOT NULL
- slug text NOT NULL UNIQUE
- attributes jsonb NOT NULL DEFAULT '{}'
- search_vector tsvector NOT NULL
- created_at timestamptz DEFAULT now()
- updated_at timestamptz DEFAULT now()
Indexes:
- uq_product_slug(slug)
- idx_product_category(category_id)
- idx_product_brand(brand_id)
- gin_product_search(search_vector) USING GIN(search_vector)    # FTS 
- gin_product_attrs(attributes) USING GIN(attributes)          # jsonb 
Optional:
- pg_trgm for fuzzy on title/slug (extension pg_trgm) 

4) product_gtin
- product_id uuid FK -> product.id
- gtin text NOT NULL
- gtin_type text NOT NULL            # GTIN-14|GTIN-13|UPC|EAN|UNKNOWN
Constraints:
- PK(product_id, gtin)
- UNIQUE(gtin)  # если ожидается уникальность; если нет — снять (не указано)
Indexes:
- idx_gtin(gtin)

Обоснование GTIN: GS1 фиксирует, что EAN/UPC штрихкоды печатаются практически на каждом consumer product, и что GTIN — ключ для идентификации товаров. 

5) provider
- id uuid PK
- type text NOT NULL                 # EXTERNAL|LOCAL
- name text NOT NULL
- slug text NOT NULL UNIQUE
- website_url text NULL
- is_active boolean DEFAULT true
Indexes:
- uq_provider_slug(slug)

6) offer
- id uuid PK
- provider_id uuid FK NOT NULL
- product_id uuid FK NULL            # NULL до матчинга
- external_id text NULL
- url text NOT NULL
- title text NOT NULL
- gtin text NULL
- currency text NOT NULL             # ISO (не указано какие)
- price_minor bigint NOT NULL
- availability text NOT NULL         # IN_STOCK|OUT_OF_STOCK|UNKNOWN
- last_seen_at timestamptz DEFAULT now()
- updated_at timestamptz DEFAULT now()
Constraints:
- UNIQUE(provider_id, external_id) WHERE external_id IS NOT NULL
- UNIQUE(provider_id, url) WHERE external_id IS NULL
Indexes:
- idx_offer_provider(provider_id)
- idx_offer_product(product_id)
- idx_offer_gtin(gtin)
- idx_offer_last_seen(last_seen_at)

7) price_snapshot
- id uuid PK
- offer_id uuid FK NOT NULL
- captured_at timestamptz NOT NULL
- currency text NOT NULL
- price_minor bigint NOT NULL
- availability text NOT NULL
Indexes:
- idx_snapshot_offer_time(offer_id, captured_at DESC)

Scale: партиционирование по captured_at (RANGE) — Postgres документирует декларативное partitioning. 

8) offer_match
- offer_id uuid FK -> offer.id
- product_id uuid FK -> product.id
- match_type text NOT NULL           # GTIN|RULE|MANUAL
- confidence numeric(4,3) NOT NULL DEFAULT 1.000
- decided_by_user_id uuid NULL
- decided_at timestamptz DEFAULT now()
Constraints:
- PK(offer_id)

9) user_identity
- id uuid PK
- auth_provider text NOT NULL
- provider_user_id text NOT NULL
- email text NULL (PII)
- phone text NULL (PII)
- created_at timestamptz DEFAULT now()
Constraints:
- UNIQUE(auth_provider, provider_user_id)

10) favorite
- user_id uuid FK
- product_id uuid FK
- created_at timestamptz DEFAULT now()
Constraints:
- PK(user_id, product_id)

11) price_alert
- id uuid PK
- user_id uuid FK
- product_id uuid FK
- direction text NOT NULL            # DROP_BELOW (MVP)
- target_price_minor bigint NOT NULL
- currency text NOT NULL
- channel text NOT NULL              # TELEGRAM|EMAIL (каналы — не указано)
- is_active boolean DEFAULT true
- created_at timestamptz DEFAULT now()
Indexes:
- idx_alert_product_active(product_id, is_active)

12) clickout_event
- id uuid PK
- offer_id uuid FK
- user_id uuid FK NULL
- session_id text NOT NULL
- ip inet NULL (PII)
- user_agent text NULL (PII)
- created_at timestamptz DEFAULT now()
```

### Prisma schema (фрагменты) и миграции

Prisma документирует индексы/уникальные ограничения (`@@index`, `@@unique`) и то, что `prisma migrate deploy` следует запускать в CI/CD для stage/prod. 

Фрагмент Prisma (tsvector лучше держать как Unsupported и создавать индекс/триггер raw SQL миграцией):

```prisma
model Product {
  id          String   @id @default(uuid())
  categoryId  String
  brandId     String?
  title       String
  slug        String   @unique
  attributes  Json     @default("{}")

  searchVector Unsupported("tsvector")

  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  @@index([categoryId])
  @@index([brandId])
}

model Offer {
  id           String   @id @default(uuid())
  providerId   String
  productId    String?
  externalId   String?
  url          String
  title        String
  gtin         String?
  currency     String
  priceMinor   BigInt
  availability String
  lastSeenAt   DateTime @default(now())
  updatedAt    DateTime @updatedAt

  @@index([providerId])
  @@index([productId])
  @@index([gtin])
}

model PriceSnapshot {
  id           String   @id @default(uuid())
  offerId      String
  capturedAt   DateTime
  currency     String
  priceMinor   BigInt
  availability String

  @@index([offerId, capturedAt(sort: Desc)])
}
```

Raw SQL миграция (примерно): создать `search_vector` через generated column/trigger и GIN индекс по `tsvector` — Postgres прямо указывает, что `tsvector` колонка подходит для GIN индекса для FTS. 

## Pipeline инжеста и качество данных

### Принципиальная модель инжеста

MVP должен поддерживать три источника данных:

- Feeds (CSV/XML/JSON): самый “чистый” и юридически устойчивый источник (партнёрства/выгрузки). (Формат/партнёрства — не указано.)
- Sitemaps: дешёвый способ собрать список карточек для обхода, если источник публикует sitemap.
- Scraping: Playwright для JS‑рендеринга и сложных страниц, с extraction через DOM/JSON‑LD и строгим rate limiting/backoff.

Playwright документирует `page.evaluate()` (выполнение JS в контексте страницы) и network APIs для отслеживания/модификации трафика, включая `page.route()`. 

### Очереди BullMQ: воркеры, retry/backoff, лимиты и расписание

BullMQ документирует:
- Retries failing jobs с backoff функциями. 
- Rate limiting через опцию `limiter { max, duration }`. 
- Concurrency на воркере (factor > 1) либо несколько процессов. 
- Job Schedulers (v5.16+) как замену repeatable jobs и поддержку cron/interval стратегий. 
- `UnrecoverableError` для “неисправимых” ошибок, чтобы остановить ретраи. 

Очереди (MVP):

- `ingest.fetch_list` — получить URL list (feed/sitemap)
- `ingest.fetch_page` — забрать HTML/JSON
- `ingest.parse_offer` — нормализовать в OfferCandidate
- `ingest.upsert_offer` — upsert offer + insert snapshot
- `match.product` — GTIN/rules/manual
- `alerts.evaluate` — проверка алертов на основании snapshots

### Snapshotting цен и SLA свежести

Сохранение истории цены — это основа для:
- “истории цены” в UI,
- price alerts,
- SLO/SLA обновления.

В Postgres это естественно выражается в отдельной таблице `price_snapshot`, а в Scale‑фазе она почти неизбежно растёт и становится кандидатом на partitioning по времени (Postgres документирует декларативное partitioning). 

SLO/SLA (значения как шаблон; финальные значения — не указано):
- SLA‑A: доля офферов, обновлённых ≤ X минут/часов
- SLA‑B: доля офферов, обновлённых ≤ Y часов
- Алёрт: если SLA‑A просел ниже Z% на N минут

### Дедупликация: GTIN → правила → ручная модерация

- Уровень 1 (GTIN): если в оффере есть GTIN/EAN/UPC, матчим через `product_gtin`. Сергейность GTIN подтверждается тем, что EAN/UPC печатаются “virtually every consumer product”, и GS1 рассматривает GTIN как ключ идентификации. 
- Уровень 2 (rules): токены из title (brand+model+memory/etc), категория, vendor patterns (набор правил — не указано).
- Уровень 3 (manual): `moderation_task` и подтверждение матча админом (UI/эндпоинт).

### Mermaid: pipeline/flow

```mermaid
flowchart TD
  A[Job Scheduler: ingest_job] --> B[Queue ingest.fetch_list]
  B --> C{mode}
  C -->|FEED| D[Parse feed -> OfferCandidates]
  C -->|SITEMAP| E[Fetch sitemap -> URL list]
  C -->|SCRAPE| F[Seed URLs -> URL list]
  E --> G[Queue ingest.fetch_page]
  F --> G
  G --> H[Playwright fetch + extract]
  H --> I[Queue ingest.parse_offer]
  I --> J[Normalize price/currency/gtin/availability]
  J --> K[Queue ingest.upsert_offer]
  K --> L[Upsert Offer]
  L --> M[Insert price_snapshot]
  L --> N[Queue match.product]
  N --> O{Match}
  O -->|GTIN| P[Match product_gtin]
  O -->|RULE| Q[Rules scoring]
  O -->|NO MATCH| R[Create moderation_task]
  M --> S[Queue alerts.evaluate]
```

### Пример BullMQ worker (fetch_page) с limiter и UnrecoverableError

```ts
import { Worker, UnrecoverableError } from "bullmq";

export const fetchPageWorker = new Worker(
  "ingest.fetch_page",
  async (job) => {
    const { url } = job.data as { url: string };

    const resp = await fetch(url, { redirect: "follow" });

    if (resp.status === 404) throw new UnrecoverableError("not_found");
    if (resp.status === 429) throw new Error("rate_limited"); // пойдёт в retry/backoff

    const html = await resp.text();
    return { html };
  },
  {
    connection: { host: "redis", port: 6379 },
    concurrency: 10, // IO-heavy, тюнинг по факту
    limiter: { max: 30, duration: 60_000 }, // пример rate limiting
  }
);
```

BullMQ документирует limiter и остановку ретраев через `UnrecoverableError`. 

## API‑контракт, авторизация и rate limits

### Базовые факты и ограничения реализации (Route Handlers)

Route Handlers в Next.js позволяют определять обработчики HTTP‑методов (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`) в файле `route.ts|js`. Это удобно для MVP‑BFF API, но требует обязательного rate limiting и RBAC, потому что endpoints публичны. 

### Авторизация и роли

Роли (MVP): `USER`, `SELLER`, `ADMIN`. Выбор провайдера аутентификации — **не указано** (может быть любая реализация, совместимая с Next.js). Next.js отдельно даёт guide по реализации auth и рекомендует декомпозировать auth‑процесс. 

Security baseline для API: OWASP подчёркивает риск Broken Object Level Authorization (BOLA) при манипуляции object IDs в path/query/payload, поэтому RBAC/ACL должны проверяться на каждый объект. 

### Rate limits (значения — не указано)

Рекомендуется минимум три лимитера:
- public search endpoints: per IP / minute
- redirect/clickout: per IP / minute + защита от накрутки
- admin: per user / minute

На периметре WAF: Cloudflare документирует rate limiting rules как способ задавать лимиты и действие при превышении (block/challenge/log). 

### REST endpoints (MVP)

Base: `/api/v1`

Public:
- GET `/health`
- GET `/categories`
- GET `/brands?q=`
- GET `/stores?type=`
- GET `/products?q=&category=&brand=&priceMin=&priceMax=&page=&pageSize=`
- GET `/products/:id`
- GET `/products/:id/offers?sort=price_asc|price_desc|updated_desc`
- GET `/offers/:id/redirect` → 302 + clickout_event

Account (auth required):
- GET `/me`
- GET `/favorites`
- POST `/favorites` { productId }
- DELETE `/favorites/:productId`
- GET `/alerts`
- POST `/alerts` { productId, direction, targetPriceMinor, currency, channel }
- PATCH `/alerts/:id` { isActive }
- DELETE `/alerts/:id`

Admin (role ADMIN):
- POST `/admin/ingest/run` { sourceId }
- GET `/admin/ingest/runs?sourceId=`
- GET `/admin/ingest/runs/:id`
- GET `/admin/moderation/tasks`
- POST `/admin/moderation/match` { offerId, productId, matchType, confidence }

Payload правила:
- `priceMinor` как integer в minor units
- `currency` как строка ISO (какие валюты — не указано)
- `availability` enum (`IN_STOCK|OUT_OF_STOCK|UNKNOWN`)

### GraphQL (опционально)

GraphQL добавить как `/api/v1/graphql` для “агрегированных” запросов (product + offers + snapshots) — **не обязательно для MVP**. Если добавляете, вводите query complexity limits и persisted queries (конкретные лимиты — не указано), иначе повышается атака‑поверхность (в том числе обход rate limit через батчинг — OWASP отмечает риски вокруг auth/rate limiting). 

## Frontend архитектура и SEO стратегия

### Структура страниц (App Router)

- `/` — landing + search box
- `/search` — динамическая выдача (SSR/dynamic)
- `/c/[...slug]` — категория (SSG/ISR)
- `/p/[slug]` — карточка товара (ISR)
- `/brand/[slug]`, `/store/[slug]` — SEO страницы (ISR)
- `/favorites`, `/alerts` — личный кабинет (dynamic, auth)

Next.js документирует механизмы кеширования и revalidation, а также отдельный guide “Caching and Revalidating”. 

### SSR/SSG/ISR: политика

- Категории и карточки товаров: ISR с revalidate (значения — не указано), плюс on‑demand invalidation при критичных обновлениях (например, major price drop, приоритетные категории).
- Search выдача: dynamic (по умолчанию), но можно кэшировать популярные запросы на сервере через Next caching primitives (реализация — не указано). 

### Metadata и sitemap

- `generateMetadata` для динамических title/description/canonical и share‑метаданных — Next.js даёт функцию generateMetadata в API reference. 
- `sitemap.(js|ts)` — специальный файл, кешируется по умолчанию (в зависимости от dynamic APIs), и поддерживает генерацию sitemap. 
- Для больших каталогов: `generateSitemaps` генерирует несколько sitemap, которые будут доступны по `/.../sitemap/[id].xml`. 

### Компоненты (MVP)

- `SearchBar`, `SearchResults`, `FiltersPanel`
- `ProductHeader`, `OfferList`, `PriceHistoryMini` (можно начать без графика: таблица последних N snapshots)
- `StoreBadge`, `ClickoutButton` (всегда через redirect endpoint, чтобы логировать clickouts)

## Эксплуатация, безопасность, тесты и roadmap MVP→Scale

### DevOps: Docker, Compose, окружения и миграции

Docker Compose предназначен для определения и запуска multi‑container приложений, а multi‑stage builds помогают отделить build‑зависимости от runtime и уменьшить размер финального образа/attack surface. 

compose.yaml (локальный dev; пример):

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: catalog
      POSTGRES_USER: catalog
      POSTGRES_PASSWORD: catalog
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  web:
    build:
      context: .
      dockerfile: infra/docker/web.Dockerfile
    environment:
      DATABASE_URL: postgresql://catalog:catalog@postgres:5432/catalog
      REDIS_URL: redis://redis:6379
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
    ports: ["3000:3000"]
    depends_on: [postgres, redis, otel-collector]

  ingest:
    build:
      context: .
      dockerfile: services/ingest/Dockerfile
    environment:
      DATABASE_URL: postgresql://catalog:catalog@postgres:5432/catalog
      REDIS_URL: redis://redis:6379
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
    depends_on: [postgres, redis, otel-collector]

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    volumes:
      - ./infra/docker/otel-collector.yaml:/etc/otelcol-contrib/config.yaml
    command: ["--config=/etc/otelcol-contrib/config.yaml"]
    ports: ["4317:4317", "4318:4318"]
```

Переменные окружения в Compose: Docker документирует `.env`/`env_file` и правила интерполяции. 

Миграции: Prisma рекомендует `migrate deploy` в CI/CD для stage/prod. 

### CI/CD: GitHub Actions (пример pipeline и таблица)

GitHub Actions документирует, что workflow — это YAML‑файл, состоящий из jobs, а секреты задаются через secrets context. Также есть официальные гайды по service containers для PostgreSQL и Redis. 

ТАБЛИЦА B — CI/CD pipeline шаги (plain text)

+-------------------+------------------------------+----------------------------------------------+
| Шаг               | Действие                     | Источник                                      |
+-------------------+------------------------------+----------------------------------------------+
| workflow YAML      | описать jobs/steps в YAML     | workflow syntax           |
| secrets            | хранить токены/ключи в secrets| using secrets             |
| service containers | поднять Postgres/Redis в CI    | Postgres/Redis containers  |
| migrations         | prisma migrate deploy          | Prisma deploy guide  |
| build/test         | lint/typecheck/unit+integration| (реализация — не указано)                     |
+-------------------+------------------------------+----------------------------------------------+

Workflow пример (CI):

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: catalog
          POSTGRES_USER: catalog
          POSTGRES_PASSWORD: catalog
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: corepack enable
      - run: npm ci

      - run: npm run lint
      - run: npm run typecheck
      - run: npm test

      - name: prisma migrate deploy
        env:
          DATABASE_URL: postgresql://catalog:catalog@localhost:5432/catalog
        run: npx prisma migrate deploy

      - run: npm run build
```

### Deploy: Railway/Render

Railway документирует, что variables используются как environment variables при build/run, а также описывает build/deploy lifecycle и environments.   
Render документирует background workers (для постоянной обработки очередей) и cron jobs (ограничения длительности run, и рекомендацию использовать worker для длительных задач). 

Рекомендованный расклад сервисов:
- Web service: Next.js (UI+BFF)
- Worker service: ingest (BullMQ workers)
- Managed Postgres, Managed Redis
- Cron (если нужно инициировать расписания отдельно, иначе job schedulers в worker)

### Observability: OpenTelemetry, метрики, алерты, SLO/SLA

OpenTelemetry описывает Collector как vendor‑agnostic компонент для receive/process/export telemetry, а также отдельно описывает signals: traces (span как unit of work) и metrics (measurement captured at runtime). 

Минимальный набор метрик (MVP):
- API:
  - `http.server.duration` p95/p99 (по endpoints)
  - `http.server.errors` (5xx/4xx)
- Ingest:
  - `ingest.run.duration`
  - `ingest.offers.upserted`
  - `ingest.errors.count`
  - `ingest.rate_limited.count`
- Data freshness:
  - `% offers свежие в SLA` (SLA значения — не указано)

OTLP exporter env vars документированы OpenTelemetry как способ конфигурировать endpoint. 

Collector config (минимальный пример; backend — не указано):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  batch:

exporters:
  logging:
    verbosity: normal

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [logging]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [logging]
```

### Безопасность и комплаенс

Robots policy: RFC9309 прямо указывает, что правила robots — не авторизация, и robots.txt не заменяет реальные меры защиты; перечисление путей в robots.txt делает их discoverable. 

Минимальный policy для MVP:
- Реестр источников: base_url, mode (FEED/SITEMAP/SCRAPE), robots_url, terms_url (не указано), owner contact (не указано), requests_per_minute.
- Kill‑switch по источнику (is_active=false).
- Журнал takedown обращений и SLA реакции (значения — не указано).

DMCA / takedown: если продукт публичный и может получать претензии правообладателей, полезно иметь DMCA‑style notice‑and‑takedown процесс. U.S. Copyright Office указывает, что регистрация авторского права не обязательна для отправки takedown notice (DMCA Section 512). Вне США детали зависят от юрисдикции (правовой контекст Узбекистана — не указан, требуется отдельная юридическая валидация). 

PII handling:
- Минимизировать хранение email/phone/ip/user_agent, включить retention и доступ‑контроль (конкретные сроки — не указано).
- Защитить object‑level доступ (BOLA) на каждом endpoint, где есть `:id`. 

WAF/rate limiting:
- На периметре: Cloudflare rate limiting rules (limit + action). 

### Тесты: unit/integration/e2e/contract и fixtures

E2E целесообразно делать на Playwright Test: Playwright документирует retries/timeout и централизованные locators как основу устойчивых тестов. 

Тестовая матрица (MVP):
- Unit: normalizers (price parsing), matching rules, GTIN validator (если реализуется)
- Integration: Prisma queries + миграции; BullMQ processors (Redis)
- E2E: /search → /p/[slug] → offers list → redirect endpoint
- Contract: golden responses на `/api/v1/search`, `/api/v1/products/:id`, `/api/v1/products/:id/offers`

Fixtures:
- `services/ingest/tests/fixtures/pages/*.html`
- `services/ingest/tests/fixtures/feeds/*.csv`
- `apps/web/tests/fixtures/api/*.json`

### MCP‑скилы и окружение Cursor

#### Что такое MCP, и почему это полезно именно для Cursor‑разработки

MCP задаёт стандарт, по которому серверы могут предоставлять клиенту три класса возможностей: resources, tools, prompts. Документация MCP прямо описывает эти три capability.   
Tools в MCP имеют имя и schema параметров; MCP спецификация описывает tools и наличие `inputSchema` на базе JSON Schema.   
Transport: MCP определяет stdio и Streamable HTTP; JSON‑RPC сообщения должны быть UTF‑8; клиенты “SHOULD support stdio whenever possible”. 

#### Базовый конфиг Cursor для MCP серверов

Пример формата `mcp.json` и расположений подтверждены инструкцией установки GitHub MCP server для Cursor:
- Global: `~/.cursor/mcp.json`
- Project-specific: `.cursor/mcp.json` в корне проекта
- Ключ конфигурации: `mcpServers`
- Поддержка Streamable HTTP для GitHub server требует Cursor v0.48.0+ (по этой инструкции)
- Примеры конфигураций: remote (url + headers) и local (docker command + args + env) 

Пример `.cursor/mcp.example.json` (без секретов; значения секретов — placeholders):

```json
{
  "mcpServers": {
    "github": {
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${GITHUB_PAT}"
      }
    },
    "catalog-devtools": {
      "command": "node",
      "args": ["tools/mcp/catalog-devtools/dist/server.js"],
      "env": {
        "CATALOG_DATABASE_URL": "${DATABASE_URL}",
        "CATALOG_REDIS_URL": "${REDIS_URL}"
      }
    }
  }
}
```

Важно по секретам: GitHub MCP пример показывает, что `env` может содержать секрет (PAT) и прокидывается в Docker через `-e` и `env` в конфиге. Для команды это означает: `.cursor/mcp.json` обычно не коммитится, а хранится локально; в репо держится только `mcp.example.json` + инструкция, как заполнить (механизм командного управления секретами — не указан). 

#### Проблема env vars в MCP и командный workaround

В обсуждениях Cursor community отмечается, что для безопасности Cursor не передаёт все локальные `.env` переменные всем MCP серверам, и рекомендуемый workaround — wrapper script, который загружает env и затем запускает MCP server. 

Пример wrapper script (MVP; путь/секреты — placeholders):

```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/mcp/run-catalog-devtools.sh
# Загружаем переменные окружения локально (файл с секретами не коммитим).
if [ -f ".env.mcp" ]; then
  set -a
  source .env.mcp
  set +a
fi

exec node tools/mcp/catalog-devtools/dist/server.js
```

#### Как реализовать “catalog-devtools” MCP server (tools для Cursor)

Рекомендованный минимум tools (skills), чтобы Cursor мог безопасно помогать разработке:

- `db_readonly_query` — read‑only SQL query (SELECT) для диагностики (prod‑доступ запрещён — policy не указано)
- `db_migrate_status` — показать применённые миграции
- `ingest_trigger` — запустить ingest run по sourceId
- `ingest_run_status` — статус ingest_run и ошибки
- `queue_stats` — длина очередей, rate limited jobs, failed jobs

Техническая база:
- MCP TypeScript SDK репозиторий описывает, что SDK работает на Node.js/Bun/Deno и включает server libraries (tools/resources/prompts) и transports (Streamable HTTP, stdio). 
- MCP “Build an MCP server” guide подчёркивает важность логирования в stderr для STDIO серверов, чтобы не повредить JSON‑RPC сообщения. 

Skeleton (TypeScript; упрощённо, как точка старта; конкретные API SDK классов могут отличаться по версии — версия SDK для проекта не указана, перед внедрением нужно зафиксировать):

```ts
// tools/mcp/catalog-devtools/src/server.ts
// Важно: для stdio не писать в stdout; логировать в stderr.
console.error("catalog-devtools mcp starting...");

// TODO: подключить MCP TypeScript SDK server и зарегистрировать tools.
// Источник по SDK возможностям/транспортам: README typescript-sdk. 
```

Если хотите, чтобы этот MCP server был “оформленным” по спецификации (tool schemas, JSON Schema 2020‑12, schema discovery), ориентируйтесь на MCP docs: tools имеют `inputSchema`, MCP использует JSON Schema (default 2020‑12), а transports — stdio/Streamable HTTP. 

### Roadmap MVP → Scale и приоритизация P0/P1/P2

ТАБЛИЦА C — MVP backlog с оценками (plain text; скорость команды/кол-во разработчиков — не указано)

+------+--------------------------------------------------------------+-------------+-----------------------------+----------+
| Pri  | Задача                                                       | Оценка (ч)  | Done criteria               | Риски    |
+------+--------------------------------------------------------------+-------------+-----------------------------+----------+
| P0   | Монорепо scaffold + packages/shared + packages/db             | 12–20       | сборка/линт/типизация ok    | низкие   |
| P0   | Postgres schema + Prisma migrations + migrate deploy в CI      | 20–40       | миграции применяются в CI   | средние  |
| P0   | Каталог API (categories/brands/products/offers)                | 30–60       | стабильные DTO + RBAC базис | средние  |
| P0   | Search API на Postgres FTS + GIN индексы                       | 30–70       | релевантность MVP уровня    | средние  |
| P0   | Web UI: /search + /p/[slug] + offers + redirect tracking       | 50–120      | SEO страницы открываются    | средние  |
| P0   | BullMQ infra: queues + schedulers + retries/backoff + limiter  | 30–60       | jobs стабильны              | высокие  |
| P0   | Feed ingest (CSV) -> offer upsert + price_snapshot             | 40–80       | идемпотентный импорт        | высокие  |
| P1   | Sitemap ingest (если применимо)                                | 30–60       | URL list + fetch pipeline   | средние  |
| P1   | Scrape ingest (Playwright) 1 источник                           | 60–140      | стабильный extraction       | высокие  |
| P1   | Дедуп: GTIN -> rules -> manual moderation (+admin endpoints)   | 60–140      | %matched растёт             | высокие  |
| P1   | Favorites + Alerts (API+UI)                                    | 30–70       | сохранение и алертинг ok    | средние  |
| P1   | OpenTelemetry (web + ingest + collector)                       | 20–50       | traces/metrics экспортятся  | средние  |
| P2   | MCP catalog-devtools server (инженерный акселератор)            | 20–60       | tools доступны в Cursor     | средние  |
| P2   | WAF/Cloudflare hardening + расширенный rate limiting           | 10–40       | защита от abuse             | средние  |
| P2   | Scale: partitioning price_snapshot + advanced search           | не указано  | зависит от объёмов          | высокие  |
+------+--------------------------------------------------------------+-------------+-----------------------------+----------+

Критерии готовности MVP (go/no‑go):
- Поиск → карточка товара → офферы → кликаут работает end‑to‑end (e2e тестом).
- Инжест обновляет цены по SLA (значения SLA — не указано, но SLO метрика реализована).
- Админ‑контур видит ingest_run ошибки и может выключить источник.
- Базовая observability: latency/error rate для API + ingest metrics (через OpenTelemetry/Collector). 