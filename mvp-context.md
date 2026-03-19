# MVP CONTEXT — E-CATALOG (UZ)

## 1. PRODUCT GOAL

Создать платформу для:

* поиска товаров
* сравнения цен
* перехода в магазин (clickout)

Это НЕ маркетплейс.
Это агрегатор.

---

## 2. MVP SCOPE (ЧТО ВХОДИТ)

✔ Каталог товаров
✔ Поиск
✔ Карточка товара
✔ Список предложений (offers)
✔ Переход в магазин (redirect)

---

## 3. НЕ ВХОДИТ В MVP

❌ Маркетплейс (заказы, оплата)
❌ CRM
❌ ML / рекомендации
❌ Elasticsearch
❌ Сложная аналитика

---

## 4. CORE ENTITIES

### Product (главная сущность)

Нормализованный товар

* id
* title
* brand
* model
* category_id
* attributes (json)

---

### Offer

Конкретное предложение товара

* id
* product_id
* provider (uzum, olcha и т.д.)
* price
* currency
* url
* availability
* last_seen_at

---

### Category

* id
* name
* slug
* parent_id

---

## 5. ОСНОВНАЯ ЛОГИКА

### 1 Product → много Offer

Product = один товар
Offer = цены из разных магазинов

---

## 6. DATA FLOW (PIPELINE)

scrape → normalize → save → show

---

## 7. SCRAPING (MVP)

Используем:

* Playwright

Правила:

* 1–2 источника максимум
* без сложной архитектуры

---

## 8. DATABASE

PostgreSQL

* Product — основная таблица
* Offer — цены
* price_snapshot — история цен

---

## 9. SEARCH

Использовать:

* PostgreSQL full-text search

НЕ использовать:

* Elasticsearch

---

## 10. API (MVP)

GET /products
GET /products/:id
GET /products/:id/offers
GET /search?q=

---

## 11. TECH STACK

Frontend:

* Next.js

Backend:

* Next.js API (Route Handlers)

Database:

* PostgreSQL + Prisma

Queue:

* Redis + BullMQ

Scraping:

* Playwright

---

## 12. АРХИТЕКТУРА

Monorepo:

apps/
web/
api/

services/
scraper/

packages/
shared/
db/

---

## 13. ПРОСТЫЕ ПРАВИЛА

* Не усложнять
* Не добавлять новые сущности
* Не делать “идеально”
* Делать быстро и стабильно

---

## 14. ЦЕЛЬ MVP

Запустить работающий продукт:

User → поиск → товар → цены → переход

---

## 15. KPI MVP

* есть товары в базе
* поиск работает
* цены отображаются
* clickout работает

---

## 16. ПОСЛЕ MVP

Добавляется:

* seller кабинет
* CRM
* analytics
* ML

НО НЕ СЕЙЧАС
