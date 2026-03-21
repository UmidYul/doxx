# MOSCRAPER → RABBITMQ → CRM
Единый migration document / implementation pack

Версия: 1.0
Статус: Ready for migration
Назначение: единый source of truth для полной миграции проекта на flow:
Scraper → RabbitMQ → CRM

--------------------------------------------------
1. EXECUTIVE DECISION
--------------------------------------------------

Фиксируем целевой вариант проекта:

- Moscraper = stateless scraper
- Moscraper НЕ хранит данные
- Moscraper делает только:
  - scraping
  - базовую нормализацию
  - публикацию событий в RabbitMQ
- CRM делает:
  - полную нормализацию
  - дедупликацию / идемпотентность
  - хранение фотографий
  - запись в БД
  - retry / DLQ / ingestion handling

Это основной и обязательный flow.

Никакой собственной БД, parse_cache, pending_events, delta storage, image storage, raw HTML storage или REST sync в CRM внутри scraper быть не должно.

--------------------------------------------------
2. ПОЧЕМУ ИМЕННО ЭТОТ ВАРИАНТ
--------------------------------------------------

Этот вариант лучше всего подходит под вашу ситуацию, потому что:

- CRM разрабатывается отдельно от вас
- интеграция должна быть простой, контрактной и независимой
- scraper не должен знать внутреннюю логику CRM
- нужно снизить связность систем
- нужно упростить будущие интеграции и масштабирование

Поэтому самый правильный принцип:
Moscraper публикует стандартизированное событие в RabbitMQ.
CRM сама решает, как это событие потреблять, обогащать, хранить и повторно обрабатывать.

Итог:
Scraper не владеет состоянием.
CRM владеет состоянием.

--------------------------------------------------
3. ВЫБРАННЫЕ СОГЛАСОВАННЫЕ РЕШЕНИЯ
--------------------------------------------------

Ниже не список “вариантов”, а уже выбранный baseline.

3.1. Message format
Выбор:
CloudEvents-compatible JSON envelope

Почему:
- слабая связность между командами
- простой договор между Moscraper и CRM
- удобно версионировать
- легко подключать новые consumers в будущем
- не заставляет CRM знать внутренние модели scraper

Важно:
Берем не “full strict enterprise CloudEvents stack everywhere”, а практичный вариант:
CloudEvents-compatible internal envelope.
То есть JSON-структура строго похожа на CloudEvents и совместима по смыслу, но без лишней тяжести.

3.2. Idempotency strategy
Выбор:
CRM должна строить идемпотентность по:
entity_key + payload_hash

Почему:
- event_id уникален для конкретной публикации, но не решает бизнес-дубликаты
- entity_key + payload_hash позволяет легко понять:
  - это тот же товар
  - это те же данные
  - или это новое изменение
- это лучше подходит для scraper-интеграции, где возможны повторы publish, перезапуски jobs и сетевые сбои

3.3. CRM integration boundary
Выбор:
между RabbitMQ и основной CRM должен быть отдельный ingestion layer / consumer boundary
(логически минимум, физически — отдельный сервис или отдельный модуль CRM)

Почему:
- CRM разрабатывается отдельно
- нужен стабильный контракт на входе
- ingestion слой сможет:
  - валидировать envelope
  - логировать invalid payload
  - делать первичный dedup
  - отправлять в DLQ
  - маршрутизировать дальше внутри CRM

Это делает интеграцию Moscraper ↔ CRM дешевле и безопаснее.

3.4. RabbitMQ topology
Выбор:
routing по типу события, а не по магазинам

Базово:
- exchange: moscraper.events
- routing key: listing.scraped.v1

Почему:
- проще для отдельной CRM-команды
- меньше хаоса в маршрутах
- добавление новых источников не ломает topology
- если потом понадобится, можно добавить store в headers/data, а не дробить routing на старте

3.5. Schema evolution
Выбор:
обязательная policy для schema_version

Почему:
CRM разрабатывается отдельно, значит контракт должен жить отдельно от кода.
Поэтому в каждом сообщении должна быть version-aware схема.

Практический вариант:
- type = com.moscraper.listing.scraped
- specversion = 1.0
- data.schema_version = 1

--------------------------------------------------
4. ОФИЦИАЛЬНЫЙ TARGET FLOW
--------------------------------------------------

Целевой pipeline:

[Store websites]
    ↓
[ Moscraper ]
    - scrape
    - minimal normalization
    - validate outbound payload
    - publish to RabbitMQ
    ↓
[ RabbitMQ ]
    ↓
[ CRM ingestion ]
    - validate message contract
    - dedup / idempotency
    - full normalization
    - image downloading/storage
    - persistence to CRM DB
    - retry / DLQ / observability

Что НЕ делает Moscraper:
- не держит свою БД
- не хранит parse_cache
- не ведет pending_events
- не хранит фото
- не делает delta against local state
- не отправляет изменения в CRM по REST
- не хранит raw HTML архив
- не использует Celery/Redis как delivery layer в CRM

--------------------------------------------------
5. BEST-FIT STACK ДЛЯ ВАШЕГО ПРОЕКТА
--------------------------------------------------

Фиксируем стек:

Core:
- Python
- Scrapy
- RabbitMQ

Publish layer:
- aio-pika
- publisher confirms
- durable exchange/queue policy
- quorum queues

Validation / contract:
- Pydantic v2

Serialization:
- orjson

Message contract:
- CloudEvents-compatible JSON envelope

Operational principles:
- at-least-once delivery
- CRM-side idempotency
- no local persistence in scraper
- fail fast on broker publish failure

--------------------------------------------------
6. MESSAGE CONTRACT
--------------------------------------------------

6.1. Envelope

Рекомендуемый envelope:

{
  "specversion": "1.0",
  "id": "uuid",
  "source": "moscraper://mediapark",
  "type": "com.moscraper.listing.scraped",
  "time": "2026-03-21T12:00:00Z",
  "datacontenttype": "application/json",
  "subject": "listing",
  "data": {
    "schema_version": 1,
    "entity_key": "mediapark:123456",
    "payload_hash": "sha256:...",
    "store": "mediapark",
    "url": "https://...",
    "source_id": "123456",
    "title": "iPhone 15 128GB",
    "price_raw": "12 999 000 сум",
    "price_value": 12999000,
    "currency": "UZS",
    "in_stock": true,
    "brand": "Apple",
    "raw_specs": {
      "memory": "128GB",
      "color": "Black"
    },
    "description": "raw description from source page",
    "image_urls": [
      "https://..."
    ],
    "scraped_at": "2026-03-21T12:00:00Z"
  }
}

6.2. Required fields
Обязательные:
- specversion
- id
- source
- type
- time
- datacontenttype
- data.schema_version
- data.entity_key
- data.payload_hash
- data.store
- data.url
- data.title
- data.scraped_at

6.3. entity_key rule
Порядок:
1. store + ":" + source_id
2. если source_id нет:
   store + ":" + canonical_url_hash

6.4. payload_hash rule
payload_hash считается на нормализованном business payload без event metadata.
Это нужно для CRM-side dedup.

--------------------------------------------------
7. RABBITMQ BASELINE
--------------------------------------------------

Рекомендуемый baseline:

- exchange: moscraper.events
- exchange type: topic
- routing key: listing.scraped.v1
- queue example: crm.listing.ingest.v1
- queue type: quorum
- delivery mode: persistent
- publisher confirms: required

Базовый принцип:
если publish не подтвержден, scraper не буферизует это локально на диск и не пишет в свою БД.
Он завершает job с ошибкой / поднимает сигнал сбоя.
Повторная доставка должна безопасно обрабатываться CRM через idempotency.

--------------------------------------------------
8. ЧТО ДОЛЖНО БЫТЬ УДАЛЕНО ИЗ ТЕКУЩЕГО ПРОЕКТА
--------------------------------------------------

Из runtime и документации нужно убрать:

Архитектурно:
- local DB in scraper
- parse_cache
- pending_events
- delta detector against scraper-owned state
- CRM REST sync path
- image/file storage in scraper
- Celery/Redis как обязательную часть delivery flow
- Alembic / scraper migrations
- Supabase / scraper-owned Postgres

Из документации:
- любые формулировки про “scraper stores data”
- любые формулировки про “ONLY deltas via scraper cache”
- любые формулировки про “parse_cache updated after CRM response”
- любые REST sync flows
- любые build prompts, возвращающие проект к DB-first scraper architecture

--------------------------------------------------
9. ЧТО ДОЛЖНО БЫТЬ ДОБАВЛЕНО
--------------------------------------------------

Нужно добавить:

Код:
- domain/messages.py
- application/message_builder.py
- infrastructure/publishers/base.py
- infrastructure/publishers/rabbitmq_publisher.py
- infrastructure/publishers/publisher_factory.py
- infrastructure/pipelines/publish_pipeline.py

Документация:
- новый PROJECT.md
- новый BUILD_PLAN.md
- новый .cursorrules
- новый scraper.mdc
- новый .env.example
- новый docker-compose.yml
- обновленный pyproject.toml

--------------------------------------------------
10. ЦЕЛЕВОЙ СОСТАВ ДОКУМЕНТАЦИИ
--------------------------------------------------

10.1. PROJECT.md должен описывать
- scraper is stateless
- target flow scraper → RabbitMQ → CRM
- contract message structure
- integration boundary with CRM
- observability and failure model
- what scraper does not own

10.2. BUILD_PLAN.md должен
- генерировать только новый flow
- не генерировать storage/database/pending_events
- не генерировать REST sync
- не генерировать delta cache
- направлять ИИ на publish-only architecture

10.3. .cursorrules должен закреплять
- no DB in scraper
- no persistence in scraper
- only publish to RabbitMQ
- CRM owns normalization/storage/state
- all outbound payloads validated by Pydantic

10.4. scraper.mdc должен
- описывать только stateless scraper behavior
- не содержать storage-oriented architecture

--------------------------------------------------
11. ГОТОВЫЕ ТЕКСТЫ ДЛЯ ДОКУМЕНТАЦИИ
--------------------------------------------------

11.1. PROJECT.md
Ниже готовый текст.

==================================================
PROJECT.md
==================================================

# MOSCRAPER PROJECT

## Overview

Moscraper is a stateless scraping service.

Its only responsibility is:
- scrape product/listing data from source websites,
- apply minimal deterministic normalization,
- validate outbound event payloads,
- publish events to RabbitMQ.

Moscraper does not own business state.

The CRM platform is the system of record and is fully responsible for:
- full normalization,
- deduplication and idempotency,
- image downloading and storage,
- persistence to database,
- retries, dead-letter handling, and downstream processing.

## Target Architecture

Store websites
→ Moscraper
→ RabbitMQ
→ CRM ingestion
→ CRM normalization / storage / media / DB

## Explicit Non-Goals

Moscraper must not:
- use its own database,
- maintain parse cache,
- store pending events,
- store product images,
- perform full business normalization,
- compare against its own historical state,
- send listing deltas directly to CRM over REST,
- own retry persistence.

## Core Runtime Responsibilities

Moscraper does:
- extraction,
- price/number/date normalization,
- light field cleanup,
- source metadata enrichment,
- event publishing.

## Message Contract

Moscraper publishes CloudEvents-compatible JSON messages.

Envelope fields:
- specversion
- id
- source
- type
- time
- datacontenttype
- subject
- data

Data fields:
- schema_version
- entity_key
- payload_hash
- store
- url
- source_id
- title
- price_raw
- price_value
- currency
- in_stock
- brand
- raw_specs
- description
- image_urls
- scraped_at

## Delivery Model

Moscraper publishes to RabbitMQ using:
- aio-pika
- publisher confirms
- persistent messages
- quorum-queue-compatible topology

Delivery semantics:
- at least once
- CRM must handle duplicates safely via idempotency

## Integration Boundary

Moscraper knows only the event contract and broker settings.
Moscraper does not know CRM internal tables, media storage, dedup rules, or persistence model.

That separation is intentional and mandatory.

==================================================

11.2. BUILD_PLAN.md
Ниже готовый текст.

==================================================
BUILD_PLAN.md
==================================================

# BUILD PLAN — MOSCRAPER RABBITMQ FLOW

## Foundation Rules

Build only the following architecture:

source websites
→ stateless scraper
→ RabbitMQ
→ CRM

Do not implement:
- scraper-owned DB
- parse_cache
- pending_events
- delta detector against local state
- image storage in scraper
- REST synchronization to CRM
- Celery/Redis delivery orchestration
- scraper-side persistence in any form

## Mandatory Stack

- Python
- Scrapy
- RabbitMQ
- aio-pika
- Pydantic v2
- orjson

## Required Components

1. domain/messages.py
   - Pydantic models for the outbound event contract

2. application/message_builder.py
   - transforms normalized item into event envelope

3. infrastructure/publishers/base.py
   - publisher interface

4. infrastructure/publishers/rabbitmq_publisher.py
   - RabbitMQ publisher using aio-pika
   - publisher confirms required

5. infrastructure/publishers/publisher_factory.py
   - builds publisher from settings

6. infrastructure/pipelines/publish_pipeline.py
   - final pipeline that publishes validated events

7. config/settings.py
   - only broker and runtime config relevant to stateless scraper

8. config/scrapy_settings.py
   - pipelines wired for validation → normalization → publish

## Normalization Policy

Scraper performs only minimal normalization:
- parse price
- parse currency
- normalize booleans
- light title cleanup
- light brand extraction
- preserve raw_specs and description as source-of-input for CRM

Scraper must not perform heavy semantic normalization that belongs to CRM.

## Failure Policy

If broker publish fails:
- do not persist locally
- do not create pending_events
- fail the run
- rely on rerun + CRM idempotency

## Contract Policy

All outbound messages must:
- be validated by Pydantic v2
- use CloudEvents-compatible JSON envelope
- include schema_version
- include entity_key
- include payload_hash

## AI Execution Rule

Any AI implementation generated from this file must preserve:
- stateless scraper
- RabbitMQ-only publish flow
- no storage inside scraper
- CRM-owned state

If repository code contradicts this document, this document wins.

==================================================

11.3. .cursorrules
Ниже готовый текст.

==================================================
.cursorrules
==================================================

You are working on Moscraper.

Non-negotiable architecture rules:

1. Moscraper is stateless.
2. Moscraper must not store business data.
3. Moscraper must not use its own DB, parse_cache, pending_events, image storage, or file persistence.
4. Moscraper must only do:
   - scraping
   - minimal normalization
   - event validation
   - publish to RabbitMQ
5. CRM owns:
   - full normalization
   - deduplication
   - idempotency
   - image storage
   - persistence
   - retry and DLQ handling
6. All outbound payloads must be validated with Pydantic v2.
7. All outbound messages must use a CloudEvents-compatible JSON envelope.
8. RabbitMQ publish must use aio-pika and publisher confirms.
9. Do not generate REST sync integration to CRM.
10. Do not reintroduce storage-oriented architecture into scraper.

If old files in the repository suggest parse_cache, delta sync, local persistence, or pending events, treat them as deprecated architecture and remove or replace them.

==================================================

11.4. scraper.mdc
Ниже готовый текст.

==================================================
scraper.mdc
==================================================

# Moscraper Operating Model

Moscraper is a stateless scraping publisher.

## Responsibilities
- scrape source websites
- extract structured listing data
- apply minimal deterministic normalization
- build outbound event payload
- publish event to RabbitMQ

## Non-Responsibilities
- no persistence
- no scraper-owned DB
- no image storage
- no local retry storage
- no delta comparison against owned historical state
- no CRM REST synchronization

## Publishing Rules
- messages are validated before publish
- messages use CloudEvents-compatible envelope
- publishing uses aio-pika
- publisher confirms are required

## Boundary
Moscraper is a producer only.
CRM is the owner of business state.

==================================================

11.5. .env.example
Ниже готовый текст.

==================================================
.env.example
==================================================

APP_ENV=development
LOG_LEVEL=INFO

BROKER_TYPE=rabbitmq
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RABBITMQ_EXCHANGE=moscraper.events
RABBITMQ_EXCHANGE_TYPE=topic
RABBITMQ_ROUTING_KEY=listing.scraped.v1
RABBITMQ_PUBLISH_MANDATORY=true

DEFAULT_CURRENCY=UZS
MESSAGE_SCHEMA_VERSION=1

==================================================

11.6. docker-compose.yml
Ниже готовый текст.

==================================================
docker-compose.yml
==================================================

version: "3.9"

services:
  rabbitmq:
    image: rabbitmq:4-management
    container_name: moscraper-rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    restart: unless-stopped

==================================================

11.7. pyproject.toml dependency direction
Не полный файл, а обязательное направление:

Оставить / добавить:
- scrapy
- pydantic
- aio-pika
- orjson

Убрать из scraper runtime:
- supabase
- sqlalchemy / alembic для scraper storage
- asyncpg / psycopg если нужны только для scraper DB
- celery
- redis
- crm REST transport dependencies, если они нужны только старому flow

--------------------------------------------------
12. IMPLEMENTATION MIGRATION PLAN
--------------------------------------------------

Порядок миграции:

Phase 1 — contract first
1. Утвердить этот документ как source of truth
2. Создать новые docs:
   - PROJECT.md
   - BUILD_PLAN.md
   - .cursorrules
   - scraper.mdc
   - .env.example
   - docker-compose.yml
3. Зафиксировать RabbitMQ-only baseline

Phase 2 — code refactor
4. Удалить delta pipeline
5. Удалить CRM REST sender path
6. Удалить pending_events logic
7. Удалить DB/cache/storage code из scraper runtime
8. Добавить message contract
9. Добавить RabbitMQ publisher
10. Добавить publish pipeline
11. Упростить normalize pipeline до minimal normalization

Phase 3 — integration hardening
12. Включить publisher confirms
13. Зафиксировать entity_key and payload_hash policy
14. Добавить structured logging
15. Проверить повторную публикацию и duplicate-safe ingestion contract

--------------------------------------------------
13. ИСПРАВЛЕННЫЙ PROMPT ДЛЯ ВАШЕГО ИИ
--------------------------------------------------

Ниже final prompt.
Это улучшенная версия, уже подстроенная под отдельную CRM-команду и RabbitMQ.

==================================================
FINAL IMPLEMENTATION PROMPT
==================================================

Твоя задача — полностью мигрировать текущий репозиторий Moscraper на целевую архитектуру:

source websites → Moscraper → RabbitMQ → CRM

Сначала внимательно прочитай приложенный migration document целиком.
Этот документ является ЕДИНСТВЕННЫМ source of truth.
Если код репозитория противоречит документу — приоритет всегда у документа.

Жесткие архитектурные правила:

1. Moscraper — stateless scraper.
2. Moscraper НЕ хранит данные.
3. Moscraper НЕ использует:
   - собственную БД,
   - parse_cache,
   - pending_events,
   - delta-хранилище,
   - image storage,
   - file persistence,
   - локальную retry persistence.
4. Moscraper делает только:
   - scraping,
   - minimal normalization,
   - validation,
   - publish в RabbitMQ.
5. CRM отвечает за:
   - full normalization,
   - deduplication,
   - idempotency,
   - image downloading/storage,
   - database persistence,
   - retry/DLQ handling.
6. Интеграция с CRM идет только через RabbitMQ.
7. Никакой REST sync integration в CRM быть не должно.
8. Все outbound payload должны валидироваться через Pydantic v2.
9. Формат сообщений:
   CloudEvents-compatible JSON envelope.
10. Сериализация:
   orjson.
11. RabbitMQ client:
   aio-pika.
12. Publish должен использовать publisher confirms.
13. Очереди и topology должны быть совместимы с quorum queues.
14. При publish failure нельзя создавать local pending storage. Нужно fail fast.

Выбранный технический baseline:
- Python
- Scrapy
- RabbitMQ
- aio-pika
- Pydantic v2
- orjson

Интеграционные правила:
- CRM разрабатывается отдельно от scraper.
- Moscraper не должен знать внутреннюю архитектуру CRM.
- Контракт между системами — только message schema.
- CRM-side idempotency должна опираться на:
  entity_key + payload_hash.
- Нужно сохранить слабую связность между Moscraper и CRM.

Нужный контракт сообщения:
- envelope:
  - specversion
  - id
  - source
  - type
  - time
  - datacontenttype
  - subject
  - data
- data:
  - schema_version
  - entity_key
  - payload_hash
  - store
  - url
  - source_id
  - title
  - price_raw
  - price_value
  - currency
  - in_stock
  - brand
  - raw_specs
  - description
  - image_urls
  - scraped_at

Твоя задача по репозиторию:

1. Найди все места, где текущий код и документация противоречат новому flow.
2. Полностью удали старую storage-oriented архитектуру scraper.
3. Удали или замени:
   - delta pipeline
   - parse_cache
   - pending_events
   - CRM REST sync
   - scraper DB/migrations
   - image persistence in scraper
   - Celery/Redis delivery logic, если она относится к старому flow
4. Добавь новый publish-only flow:
   - domain/messages.py
   - application/message_builder.py
   - infrastructure/publishers/base.py
   - infrastructure/publishers/rabbitmq_publisher.py
   - infrastructure/publishers/publisher_factory.py
   - infrastructure/pipelines/publish_pipeline.py
5. Упрости normalization до minimal normalization.
6. Перепиши документацию полностью:
   - PROJECT.md
   - BUILD_PLAN.md
   - .cursorrules
   - scraper.mdc
   - .env.example
   - docker-compose.yml
7. Обнови pyproject.toml под stateless scraper + RabbitMQ publish.
8. Подготовь точные patch/diff изменения по файлам.

Формат ответа:

1. Extracted target rules
2. Repository conflicts
3. Migration plan by file
4. Exact patches / diffs
5. Risks and notes
6. Optional improvements for discussion only

Запрещено:
- возвращать storage в scraper
- возвращать DB/cache/pending events
- возвращать REST sync to CRM
- заменять RabbitMQ на другой основной транспорт
- молча внедрять архитектурные нововведения вне target flow

Если хочешь предложить улучшения — выноси их отдельно в блок:
“Discussion only”.
Не внедряй их без явного подтверждения.

==================================================

--------------------------------------------------
14. ЧТО ИМЕННО ВАМ ДЕЛАТЬ ДАЛЬШЕ
--------------------------------------------------

Пошагово:

1. Возьмите этот документ как главный эталон.
2. Передайте своему ИИ:
   - этот документ
   - текущий репозиторий
   - FINAL IMPLEMENTATION PROMPT из раздела 13
3. Попросите ИИ:
   - сначала выявить конфликты
   - потом дать patch plan
   - потом переписать документы
   - потом переписать код
4. После этого отдельно проверьте:
   - в проекте не осталось DB/cache/persistence логики
   - publish идет только в RabbitMQ
   - envelope соответствует контракту
   - CRM boundary остался слабосвязанным
5. Только после этого переходите к реализации CRM-side consumer logic.

--------------------------------------------------
15. DISCUSSION ONLY
--------------------------------------------------

Ниже не внедрять молча. Это следующий этап.

Можно рассмотреть позже:
- отдельный schema registry
- отдельный dedicated CRM ingestion service
- multi-event types beyond listing.scraped
- трассировку через correlation_id / traceparent
- подпись сообщений или HMAC для межсервисной верификации
- отдельные exchange patterns для разных доменов
- retry topology на стороне CRM с DLX/DLQ policy

Сейчас это не baseline.
Сейчас baseline — простой, надежный, contract-first Moscraper → RabbitMQ → CRM.

--------------------------------------------------
16. FINAL BASELINE
--------------------------------------------------

Финально зафиксировано:

- Moscraper = stateless publisher
- RabbitMQ = единственный транспорт
- aio-pika = RabbitMQ client
- publisher confirms = обязательно
- quorum queue compatible topology = обязательно
- Pydantic v2 = contract validation
- orjson = serialization
- CloudEvents-compatible JSON = integration contract
- CRM owns all state

Это и есть рекомендуемый production direction для вашего проекта с учетом:
- отдельной разработки CRM,
- необходимости легкой интеграции,
- будущего масштабирования,
- снижения архитектурных конфликтов.
