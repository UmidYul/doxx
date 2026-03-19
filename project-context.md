# PROJECT: UZ E-CATALOG PLATFORM

## OVERVIEW
Платформа агрегирует товары из интернет-магазинов Узбекистана и предоставляет маркетплейс для локальных продавцов.

Это НЕ просто каталог.
Это data platform:
- агрегатор цен
- marketplace
- будущий CRM

---

## CORE ENTITIES

### Product
Нормализованный товар

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
Конкретное предложение товара

Поля:
- id
- product_id
- seller_id
- source (uzum, olcha)
- price
- currency
- url
- availability
- raw_data (json)

---

### Seller
Продавец

Поля:
- id
- name
- type (marketplace | external)
- rating
- created_at

---

### Category
Категории товаров

---

## KEY LOGIC

### 1. Deduplication
Один товар может приходить с разных сайтов

Match по:
- brand
- model
- title similarity

---

### 2. Search
Поиск идет через Elasticsearch:
- full-text
- фильтры
- сортировка

---

### 3. Scraping Pipeline

1. Scheduler запускает scraping
2. Job отправляется в очередь (BullMQ)
3. Worker парсит страницу
4. Данные нормализуются
5. Сохраняются в PostgreSQL
6. Индексируются в Elasticsearch

---

### 4. Seller System
- продавец может добавлять товары
- управляет своими офферами
- получает лиды

---

### 5. Telegram Integration
- уведомления о лидах
- уведомления о заказах
- будущий CRM через чат

---

## API PRINCIPLES

- REST
- pagination обязательна
- filters обязательны
- response через DTO

---

## MVP SCOPE

- scraping 3 магазинов (Uzum, Olcha, Mediapark)
- каталог товаров
- поиск
- карточка товара
- базовый seller кабинет

---

## NON-FUNCTIONAL

- scalable
- fault-tolerant scraping
- anti-bot ready
- fast search (<300ms)

---

## FUTURE

- ML deduplication
- recommendation system
- full CRM
- mobile app