# PROJECT: UZ E-CATALOG (MVP = CATALOG AGGREGATOR)

## AI PRIORITY (FOR CURSOR)
1. .cursorrules
2. ai-context.md
3. mvp-context.md
4. project-context.md
5. product-context.md
6. deep-research-report.md

## OVERVIEW
Платформа агрегирует товары из интернет-магазинов Узбекистана и помогает пользователю:
- найти товар
- сравнить цены/наличие
- перейти в магазин (clickout)

MVP = агрегатор (без заказов/оплаты).

## OUT OF MVP (HANDOFF)
- marketplace (заказы/оплата/логистика/возвраты)
- CRM
- seller portal / multi-tenant
- Elasticsearch (как отдельный сервис поиска)
- Telegram лиды/заказы (CRM-потоки)

---

## CORE ENTITIES

### Product
Нормализованный товар.

Поля:
- id
- title
- brand
- model
- category_id
- attributes (json)
- created_at

---

### Offer
Конкретное предложение товара.

Поля:
- id
- product_id
- store_id
- source (uzum, olcha, mediapark)
- price
- currency
- url
- availability
- raw_data (json)

---

### Provider (Store)
Источник/магазин (внешний провайдер цен).

Поля:
- id
- name
- type (external)
- rating
- created_at

---

### Category
Категории товаров.

---

## KEY LOGIC

### 1. Deduplication
Один товар может приходить с разных сайтов.

Match по:
- brand
- model
- title similarity

---

### 2. Search (MVP)
MVP: PostgreSQL full-text search.
P2: Elasticsearch/OpenSearch — только если упираемся в релевантность/нагрузку.

---

### 3. Ingestion Pipeline (MVP)
1. Scheduler запускает ingest/scraping
2. Job отправляется в очередь (BullMQ)
3. Worker парсит страницу/источник
4. Данные нормализуются
5. Сохраняются в PostgreSQL
6. (P2) Индексация в Elasticsearch/OpenSearch — не в MVP

---

### 4. Seller System
НЕ ВХОДИТ В MVP (см. OUT OF MVP).

---

### 5. Telegram Integration
НЕ ВХОДИТ В MVP (в MVP допустимы только простые алерты цены — если решено; сейчас не указано).

---

## API PRINCIPLES
- REST
- pagination обязательна
- filters обязательны
- response через DTO

---

## MVP SCOPE
- 1–2 источника данных максимум (scraping или CSV feed)
- каталог товаров
- поиск (Postgres FTS)
- карточка товара
- offers list
- clickout (redirect)

---

## NON-FUNCTIONAL
- scalable
- fault-tolerant ingestion
- anti-bot ready
- fast search (<300ms)

---

## FUTURE
- ML deduplication
- recommendation system
- full CRM
- mobile app
