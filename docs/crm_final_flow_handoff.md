# CRM <-> Scraper Rabbit Contract

## Purpose

Этот документ является **единым source of truth** для интеграции:

- `scraper / publisher / outbox`
- `RabbitMQ`
- `CRM scraper-consumer`
- `Supabase catalog persistence`

Его цель: описать **точный контракт сообщения**, **ожидаемое поведение CRM**, **обнаруженные реальные ошибки**, и **план исправления** для scraper/publisher AI.

## Runtime Boundary

Итоговый runtime flow:

`Scraper spider -> scraper SQLite -> publication_outbox -> publisher -> RabbitMQ -> CRM consumer -> CRM persistence -> UI`

Граница ответственности:

- До успешной публикации в RabbitMQ отвечает `scraper / publisher`.
- После доставки в очередь `crm.products.import.v1` отвечает `CRM`.

## RabbitMQ Topology

- Broker URL: `amqp://moscraper_crm:moscraper_crm_2026_secure@192.168.1.56:5672/moscraper`
- Producer exchange: `moscraper.events`
- Exchange type: `topic`
- Main routing key: `listing.scraped.v1`
- CRM consume queue: `crm.products.import.v1`
- CRM retry exchange: `crm.products.retry`
- CRM retry keys: `30s`, `5m`, `30m`
- CRM DLX: `crm.products.dlx`
- CRM DLQ: `crm.products.import.v1.dlq`

Важно:

- CRM **не** публикует первичные scraper events обратно в RabbitMQ.
- CRM **только** consume/validate/dedupe/persist.
- Внутренняя очередь scraper `scraper.products.v1` не является CRM queue и служит только observability/внутреннему контуру scraper.

## AMQP Envelope Requirements

CRM валидирует не только JSON body, но и AMQP envelope.

Обязательно:

- `content_type = application/json`
- `properties.type = scraper.product.scraped.v1` если `type` вообще передан
- Сообщение должно публиковаться как durable/persistent

Если `content_type` неверный или JSON невалидный, сообщение идёт в `scraper_incoming_rejections` и затем в DLQ.

## Canonical Message Contract

### Top-level fields

| Field | Type | Required | Notes |
|------|------|----------|------|
| `event_id` | string | yes | Глобальный event-level dedupe key |
| `event_type` | literal | yes | Только `scraper.product.scraped.v1` |
| `schema_version` | literal number | yes | Только `1` |
| `scrape_run_id` | string | yes | Batch/run ID |
| `store_name` | string | yes | Источник: `uzum`, `mediapark`, etc |
| `source_id` | string \| null | yes | Может быть `null` |
| `source_url` | string URL | yes | Валидный URL |
| `scraped_at` | string datetime | yes | ISO datetime |
| `payload_hash` | string | yes | Upstream-computed hash, CRM не пересчитывает |
| `structured_payload` | object | yes | См. ниже |
| `publication` | object | yes | Strict observability metadata |

### `structured_payload`

| Field | Type | Required | Notes |
|------|------|----------|------|
| `store_name` | string | yes | Должен совпадать с top-level `store_name` |
| `source_url` | string URL | yes | Должен совпадать с top-level `source_url` |
| `source_id` | string \| null | yes | Должен совпадать с top-level `source_id` |
| `title` | string | yes | Не пустой |
| `brand` | string \| null | yes | Nullable |
| `price_raw` | string \| null | yes | Nullable |
| `in_stock` | boolean | yes | Только boolean |
| `raw_specs` | object | yes | Именно JSON object |
| `image_urls` | string[] | yes | Все элементы валидные URL, максимум 100 |
| `description` | string \| null | yes | Nullable |
| `category_hint` | string \| null | yes | Nullable |
| `external_ids` | object | yes | Именно JSON object |
| `scraped_at` | string datetime | yes | Должен совпадать с top-level `scraped_at` |
| `payload_hash` | string | yes | Должен совпадать с top-level `payload_hash` |
| `raw_payload_snapshot` | any JSON | yes | Любой JSON |
| `scrape_run_id` | string | yes | Должен совпадать с top-level `scrape_run_id` |
| `identity_key` | string | yes | Главный source-product identity key |

### `publication`

Это **observability metadata**, а не бизнес-ключи. Но CRM валидирует этот блок строго, поэтому обязательные поля должны быть заполнены корректно.

| Field | Type | Required | Notes |
|------|------|----------|------|
| `publication_version` | number or non-empty string | yes | Обычно `1` |
| `exchange_name` | string | yes | Обычно `moscraper.events` |
| `queue_name` | string | yes | Может быть внутренняя очередь scraper |
| `routing_key` | string | yes | Обычно `listing.scraped.v1` |
| `outbox_status` | string | yes | Для реально опубликованного события должен быть `published` |
| `attempt_number` | integer >= 0 | yes | Номер publish attempt |
| `publisher_service` | string | yes | **Не может быть null** |
| `outbox_created_at` | string datetime | yes | ISO datetime |
| `published_at` | string datetime or null | yes | Schema допускает `null`, но для реально опубликованного события должен быть timestamp |

## Cross-field Invariants

CRM требует совпадения верхнеуровневых полей с дублями в `structured_payload`.

Обязательно должны совпадать:

- `store_name == structured_payload.store_name`
- `source_url == structured_payload.source_url`
- `source_id == structured_payload.source_id`
- `scraped_at == structured_payload.scraped_at`
- `payload_hash == structured_payload.payload_hash`
- `scrape_run_id == structured_payload.scrape_run_id`

Нарушение любого из этих правил приводит к reject до inbox.

## Minimal Valid Event Example

```json
{
  "event_id": "11111111-2222-3333-4444-555555555555",
  "event_type": "scraper.product.scraped.v1",
  "schema_version": 1,
  "scrape_run_id": "uzum:run-20260412-0001",
  "store_name": "uzum",
  "source_id": "sku:9434915",
  "source_url": "https://uzum.uz/ru/product/example?skuId=9434915",
  "scraped_at": "2026-04-12T08:00:00.000Z",
  "payload_hash": "sha256:example",
  "structured_payload": {
    "store_name": "uzum",
    "source_url": "https://uzum.uz/ru/product/example?skuId=9434915",
    "source_id": "sku:9434915",
    "title": "Redmi Note 14",
    "brand": "Redmi",
    "price_raw": "1969000 сум",
    "in_stock": true,
    "raw_specs": {
      "Цвет": "Фиолетовый",
      "Память": "8GB | 256GB"
    },
    "image_urls": [
      "https://images.uzum.uz/example-1.jpg"
    ],
    "description": "Описание товара",
    "category_hint": "phone",
    "external_ids": {
      "uzum": "sku:9434915"
    },
    "scraped_at": "2026-04-12T08:00:00.000Z",
    "payload_hash": "sha256:example",
    "raw_payload_snapshot": {
      "source": "uzum"
    },
    "scrape_run_id": "uzum:run-20260412-0001",
    "identity_key": "uzum:sku:9434915"
  },
  "publication": {
    "publication_version": 1,
    "exchange_name": "moscraper.events",
    "queue_name": "scraper.products.v1",
    "routing_key": "listing.scraped.v1",
    "outbox_status": "published",
    "attempt_number": 1,
    "publisher_service": "publisher-service",
    "outbox_created_at": "2026-04-12T08:00:00.000Z",
    "published_at": "2026-04-12T08:00:01.123Z"
  }
}
```

## CRM Processing Rules

### Success path

1. Consume из `crm.products.import.v1`
2. Validate AMQP envelope + JSON + Zod contract
3. Persist в `scraper_incoming_events`
4. Dedupe по `event_id`
5. Dedupe по `identity_key + payload_hash`
6. Persist catalog-side data через RPC `crm_scraper_persist_catalog_event`
7. Update inbox status to `processed`
8. `ack`

### Duplicate path

1. Сообщение валидно
2. Dedupe match по `event_id` или `identity_key + payload_hash`
3. Inbox status -> `duplicate`
4. `ack`

### Retry path

Для retryable DB/network failures:

1. Inbox status -> `failed`
2. Publish retry copy в `crm.products.retry`
3. Retry keys по стадиям: `30s -> 5m -> 30m`
4. Original message ack only after successful retry publish

### Terminal path

Для invalid или terminal business errors:

1. Если payload invalid до inbox -> row в `scraper_incoming_rejections`
2. Если ошибка после inbox -> inbox status `quarantined`
3. Rabbit message -> reject without requeue
4. Сообщение попадает в DLQ

## What CRM Stores

### `scraper_incoming_events`

Хранит:

- валидный raw event
- `publication_json`
- headers
- `process_status`
- `error_message`
- timestamps

Это **transport/inbox boundary**, а не финальная бизнес-таблица.

### `scraper_incoming_rejections`

Хранит:

- invalid payload до inbox
- `validation_error`
- `raw_body`
- `parsed_json` если JSON уже распарсился

### Catalog-side effects

После успешной inbox/idempotency обработки CRM пишет в:

- `products`
- `product_source_refs`
- `product_descriptions`
- `catalog_review_tasks`

## What Was Actually Observed In Production

Ниже не теоретические гипотезы, а подтверждённые факты из live DB / логов.

### 1. Validation reject: `publisher_service = null`

Пачка из 12 `phone`-событий (`uzum`) не попала в inbox и оказалась в `scraper_incoming_rejections`.

Факт:

- `validation_error = 'Expected string, received null'`
- `parsed_json.publication.publisher_service = null`
- `parsed_json.publication.outbox_status = 'pending'`
- `parsed_json.publication.published_at = null`

Вывод:

- publisher отправлял JSON, где `publication` не соответствовал уже опубликованному событию
- это не ошибка CRM
- это жесткий contract failure upstream

### 2. Semantic drift in `publication`

Даже если schema пропустила бы `published_at = null`, тело сообщения не должно говорить `pending/null`, когда scraper side уже утверждает `published`.

Желаемая политика:

- body, ушедший в Rabbit, должен отражать **финальное состояние publish attempt**
- нельзя публиковать stale snapshot из outbox со старыми `pending/null`

### 3. Historical `quarantined`: old consumer runtime / stale process

В live DB есть большое число `quarantined` с ошибкой:

- `Catalog persistence вернул некорректный результат.`

Но отдельная проверка показала:

- на remote функция `crm_scraper_persist_catalog_event(jsonb)` уже возвращает правильные поля `result_*`
- прямой вызов `supabase.rpc(...)` из текущего CRM кода уже получает корректный ответ:
  - `result_product_id`
  - `result_source_ref_id`
  - `result_created`
  - `result_review_task_id`

Вывод:

- эта ошибка, скорее всего, была произведена **старым запущенным consumer process**, поднятым **до** фикса маппинга `result_*`
- после изменения contract/mapper consumer нужно **обязательно перезапускать**

### 4. Historical `failed`: old RPC bug in Postgres

Есть исторические `failed` с ошибкой:

- `column reference "product_id" is ambiguous`

Это был отдельный старый баг в PL/pgSQL RPC и он уже исправлен в DB.

### 5. Transport/runtime instability

В логах consumer уже наблюдались:

- `read ECONNRESET`
- `connect ENETUNREACH 192.168.1.56:5672`
- `getaddrinfo ENOTFOUND javilkssasnyltibvfxn.supabase.co`

Вывод:

- часть проблем не связана с payload schema
- есть отдельный слой сетевой нестабильности между CRM host, Rabbit и Supabase

### 6. Data quality issue in `raw_specs`

В одном из `mediapark` payload в `raw_specs` попали фрагменты фронтенд-гидратации, например строки вида:

- `self.__next_f.push(...)`

Это не ломает schema, но ухудшает качество каталога и поиска.

Вывод:

- scraper extraction нужно чистить от page-framework noise
- `raw_specs` должен содержать только доменные характеристики товара

## Current Measured Status

По live DB за последние 7 дней:

- `scraper_incoming_events.processed`: **30**
- `scraper_incoming_events.duplicate`: **1**
- `scraper_incoming_events.failed`: **3**
- `scraper_incoming_events.quarantined`: **86**
- `scraper_incoming_rejections` validation errors: **12**

Группы ошибок:

- `Expected string, received null` -> validation reject до inbox
- `Catalog persistence вернул некорректный результат.` -> исторический stale consumer runtime
- `Не удалось проверить дубликат scraper события.` -> transport / Supabase access problem
- `column reference "product_id" is ambiguous` -> исторический старый RPC bug

## Source of Truth Rules For Scraper AI

Если scraper AI исправляет publisher, он должен считать обязательными следующие правила:

1. **Не публиковать stale JSON snapshot из outbox**
   Перед `basic.publish` body должен содержать финальные `publication.*` поля текущей попытки.

2. **`publisher_service` всегда непустая строка**
   Никогда не `null`.

3. **`outbox_status` в body должен быть согласован с фактом**
   Для реально отправленного сообщения: `published`.

4. **`published_at` должен быть заполнен для реально опубликованного события**
   Schema допускает `null`, но runtime handoff должен использовать timestamp.

5. **Дублируемые поля top-level и `structured_payload` должны совпадать**
   Нельзя, чтобы `source_id` или `payload_hash` отличались между уровнями.

6. **`raw_specs` и `external_ids` должны быть JSON object**
   Не строки, не массивы.

7. **`image_urls` — только валидные URL и максимум 100**

8. **`content_type` и `properties.type` должны соответствовать CRM contract**

9. **`payload_hash` и `identity_key` принадлежат upstream**
   CRM их не пересчитывает, поэтому scraper обязан публиковать стабильные значения.

10. **После изменения CRM consumer кода process нужно перезапускать**
    Нельзя рассчитывать, что long-running worker подхватит новый mapper без restart.

## Recommended Publisher Algorithm

Правильная логика publisher должна быть такой:

1. Прочитать pending outbox row.
2. Посчитать текущий `attempt_number`.
3. Сформировать `publish_timestamp_utc`.
4. Собрать **final event body** для Rabbit с:
   - `outbox_status = "published"`
   - `publisher_service = "<non-empty service name>"`
   - `published_at = publish_timestamp_utc`
   - корректными top-level / structured_payload дубликатами
5. Установить AMQP properties:
   - `contentType = "application/json"`
   - `type = "scraper.product.scraped.v1"`
   - persistent delivery
6. Выполнить publish в:
   - exchange `moscraper.events`
   - routing key `listing.scraped.v1`
7. Дождаться broker confirm.
8. Только после confirm обновить outbox row в SQLite как `published`.
9. Если publish не удался:
   - не оставлять расходящийся body-state как будто он уже published
   - либо пересобирать body на следующую попытку, либо хранить body snapshot вместе с актуальным attempt metadata

## CRM-side Remediation Plan

### P0. Fix publisher contract

Обязательно исправить на scraper side:

- `publication.publisher_service`
- `publication.outbox_status`
- `publication.published_at`
- согласованность top-level <-> `structured_payload`

Без этого CRM продолжит валидно отправлять сообщения в `scraper_incoming_rejections` и DLQ.

### P0. Restart / redeploy CRM consumer after code changes

Так как consumer long-running, после фиксов:

- перезапустить процесс consumer
- убедиться, что нет старого экземпляра с устаревшим mapper

### P1. Stabilize network path

Проверить:

- доступность `192.168.1.56:5672` с CRM host
- DNS resolution / HTTP reachability до `*.supabase.co`
- отсутствие кратковременных `ECONNRESET`

### P1. Clean scraper extraction quality

Убрать из `raw_specs`:

- Next.js hydration noise
- служебные page-script fragments
- строки UI/оператора, не являющиеся характеристиками товара

### P2. Add release validation

Перед массовой отправкой batch publisher должен иметь smoke check:

- сформировать body
- провалидировать его локально тем же JSON schema/contract
- проверить обязательные `publication.*`
- логировать финальный body snapshot для проблемных retries

## Acceptance Criteria

Исправление можно считать завершённым, если одновременно выполняется всё ниже:

1. Новые события не попадают в `scraper_incoming_rejections` с `Expected string, received null`.
2. Новые валидные события появляются в `scraper_incoming_events`.
3. По ним виден `process_status = processed` или `duplicate`, а не `quarantined`.
4. В `product_source_refs` / `products` появляются соответствующие изменения.
5. В Rabbit:
   - `crm.products.import.v1` не накапливает long-lived unacked
   - DLQ не растёт на валидных payload
6. После деплоя нового CRM consumer нет новых `Catalog persistence вернул некорректный результат.`

## Verification SQL

### Inbox by event_id

```sql
select event_id, process_status, error_message, received_at, processed_at
from public.scraper_incoming_events
where event_id = '<event_id>';
```

### Rejections by event_id

```sql
select event_id, process_status, validation_error, received_at
from public.scraper_incoming_rejections
where event_id = '<event_id>';
```

### Detect null `publisher_service`

```sql
select event_id,
       validation_error,
       parsed_json #>> '{publication,publisher_service}' as publisher_service,
       parsed_json #>> '{publication,outbox_status}' as outbox_status,
       received_at
from public.scraper_incoming_rejections
where validation_error = 'Expected string, received null'
  and (parsed_json #>> '{publication,publisher_service}') is null
order by received_at desc
limit 50;
```

### Recent inbox error groups

```sql
select left(coalesce(error_message,''),200) as error_message,
       process_status,
       count(*) as cnt
from public.scraper_incoming_events
where received_at >= now() - interval '7 days'
  and process_status in ('failed','quarantined')
group by process_status, left(coalesce(error_message,''),200)
order by cnt desc;
```

## Final Instruction To Scraper AI

Если scraper AI исправляет publisher, его задача не “просто отправить JSON в Rabbit”, а:

- собрать **ровно тот contract**, который требует CRM
- публиковать **согласованный final event body**
- не оставлять `null`/stale значения в `publication`
- не загрязнять `raw_specs`
- не нарушать top-level / `structured_payload` invariants

Иначе CRM **корректно** продолжит отвергать сообщения как invalid/quarantine.
# Final CRM Integration Flow

## Purpose

Согласованный runtime flow между scraper/publisher и CRM Rabbit consumer, плюс **SQL под реальную схему Postgres в репозитории** (`public.scraper_incoming_events`, `public.scraper_incoming_rejections`, `public.product_source_refs`).

## Agreed Runtime Flow

`Scraper spider -> scraper SQLite -> publication_outbox -> publisher -> RabbitMQ -> CRM consumer -> CRM persistence`

- До успешного publish в Rabbit — зона scraper.
- После потребления из очереди — зона CRM.

## RabbitMQ Connection

Актуальный broker (из handoff; в деплое подставлять свой):

```env
amqp://moscraper_crm:moscraper_crm_2026_secure@192.168.1.56:5672/moscraper
```

Consumer queue: **`crm.products.import.v1`** (не `scraper.products.v1`).

## RabbitMQ Topology

- Exchange: `moscraper.events` (topic), routing key: `listing.scraped.v1`
- CRM main queue: `crm.products.import.v1`
- Retry: `crm.products.retry` (ключи `30s`, `5m`, `30m`)
- Requeue: `crm.products.requeue`
- DLX: `crm.products.dlx`
- DLQ: `crm.products.import.v1.dlq`

## Message Contract

- `event_type = scraper.product.scraped.v1`, `schema_version = 1`
- `source_id` может быть null
- Стабильная идентичность: `structured_payload.identity_key`
- `payload_hash` — как от producer, без пересчёта в CRM
- `publication` — только delivery metadata

## Publisher / outbox: обязательные поля `publication` (иначе CRM отклонит до inbox)

CRM валидирует тело сообщения **до** записи в `scraper_incoming_events`. Блок `publication` — **strict** Zod-объект: любое обязательное поле с `null` даёт отказ, строка в `scraper_incoming_rejections.validation_error` вида `Expected string, received null`, сообщение уходит в **reject / DLQ**.

Обязательные поля (все — непустые строки, кроме указанных):

| Поле | Тип | Примечание |
|------|-----|------------|
| `publication_version` | number ≥ 1 или непустая строка | Обычно `1` |
| `exchange_name` | string | Например `moscraper.events` |
| `queue_name` | string | Observability (может быть внутренняя очередь scraper, например `scraper.products.v1`) |
| `routing_key` | string | Например `listing.scraped.v1` |
| `outbox_status` | string | Должно отражать факт; для успешно опубликованного — **`published`** |
| `attempt_number` | number ≥ 0 | Обычно `1` при первой публикации |
| **`publisher_service`** | **string, не null** | Частая ошибка: **`null` → отказ CRM** |
| `outbox_created_at` | string, ISO datetime | |
| `published_at` | string ISO datetime **или** `null` | После успешного publish лучше передавать **UTC timestamp** |

### Минимальный корректный пример `publication`

```json
"publication": {
  "publication_version": 1,
  "exchange_name": "moscraper.events",
  "queue_name": "scraper.products.v1",
  "routing_key": "listing.scraped.v1",
  "outbox_status": "published",
  "attempt_number": 1,
  "publisher_service": "publisher-service",
  "outbox_created_at": "2026-04-12T07:00:00.000Z",
  "published_at": "2026-04-12T07:00:01.234Z"
}
```

### Что было не так у пачки phone / uzum (12 событий)

В сохранённом `parsed_json` отклонённых сообщений одновременно:

- `publication.publisher_service`: **`null`**
- `publication.outbox_status`: **`pending`**
- `publication.published_at`: **`null`**

То есть в Rabbit ушёл JSON, **не соответствующий** состоянию «уже published» на стороне outbox. Исправление: **перед** `basic.publish` обновить в памяти/в SQLite финальный envelope события (или собирать body только после commit outbox в `published`).

### SQL: найти отклонения из‑за пустого `publisher_service`

```sql
select event_id,
       validation_error,
       parsed_json #>> '{publication,publisher_service}' as publisher_service,
       parsed_json #>> '{publication,outbox_status}'     as outbox_status,
       received_at
from public.scraper_incoming_rejections
where validation_error = 'Expected string, received null'
  and (parsed_json #>> '{publication,publisher_service}') is null
order by received_at desc
limit 50;
```

## CRM Processing Rules (кратко)

1. Сообщение из `crm.products.import.v1`
2. Валидация JSON и контракта
3. Запись в inbox (`scraper_incoming_events`) + raw
4. Dedupe по `event_id` и по `identity_key` + `payload_hash`
5. Catalog persistence (RPC `crm_scraper_persist_catalog_event`) → `products` / `product_source_refs` / описания / review tasks
6. Статус inbound → `processed` / `duplicate` / `failed` / `quarantined`
7. Ack / retry / reject по политике consumer (см. `apps/crm/src/modules/scraper-consumer/README.md`)

## Real Test Events

### Свежий event

- `event_id`: `36634eb0-f194-5637-ac8e-ca8989255fc6`
- `store_name`: `mediapark`
- `source_id`: `40`
- `payload_hash`: `sha256:581a21450d55dcc9fb90fd61330f07cc02c0ddf64c90b773a9001d8f51dc58fc`
- `scrape_run_id`: `mediapark:a3a6e8ffba0441a8957967eb2d23793b`

### Ранний event

- `event_id`: `a7218a99-8b53-5686-8524-005ca3f63987`
- `payload_hash`: `sha256:99f71d925900ea7fb150f72635d6ce8b2cd992b657df6d2ff0d00f4f05acf6b5`

---

## Schema alignment (важно)

Таблицы в CRM **не содержат** колонок из старых черновиков handoff:

| Было в черновике SQL | В реальной БД |
|----------------------|----------------|
| `scraper_incoming_rejections.reason_code`, `error_message`, `payload_hash` | Есть **`validation_error`**, **`process_status`** (= `'invalid'`), **`raw_body`**, **`parsed_json`**, **`headers_json`**, **`received_at`** — **нет** `reason_code` / `payload_hash` в этой таблице |
| `product_source_refs.source_system`, `source_store`, `is_active` | Есть **`source_type`**, **`source_name`**, **`identity_key`**, **`external_id`**, **`is_primary`**, **`first_seen_at`**, **`last_seen_at`** — **нет** `source_store` / `is_active` |

Inbox: `scraper_incoming_events` — колонки совпадают с запросом 1 ниже (префикс `public.` опционален).

---

## SQL Verification Queries (исправлены под схему репо)

### Query 1: inbound event by event_id

```sql
select
  id,
  event_id,
  event_type,
  store_name,
  source_id,
  source_url,
  payload_hash,
  process_status,
  error_message,
  received_at,
  processed_at,
  created_at,
  updated_at
from public.scraper_incoming_events
where event_id = '36634eb0-f194-5637-ac8e-ca8989255fc6'
order by created_at desc;
```

### Query 2: rejection (invalid до inbox) by event_id

```sql
select
  id,
  event_id,
  process_status,
  validation_error,
  content_type,
  message_type,
  received_at,
  created_at,
  updated_at
from public.scraper_incoming_rejections
where event_id = '36634eb0-f194-5637-ac8e-ca8989255fc6'
order by created_at desc;
```

### Query 3: source-ref activity (scraper + mediapark + listing 40)

```sql
select
  id,
  source_type,
  source_name,
  identity_key,
  external_id,
  product_id,
  is_primary,
  payload_hash,
  first_seen_at,
  last_seen_at,
  created_at,
  updated_at
from public.product_source_refs
where source_type = 'scraper'
  and source_name = 'mediapark'
  and (
    external_id = '40'
    or identity_key = 'mediapark:40'
  )
order by updated_at desc nulls last, created_at desc;
```

### Query 4: correlate inbound and source refs

```sql
with incoming as (
  select
    event_id,
    store_name,
    source_id,
    payload_hash,
    process_status,
    error_message,
    processed_at,
    created_at
  from public.scraper_incoming_events
  where event_id = '36634eb0-f194-5637-ac8e-ca8989255fc6'
)
select
  i.event_id,
  i.store_name,
  i.source_id,
  i.payload_hash,
  i.process_status,
  i.error_message,
  i.processed_at,
  i.created_at as incoming_created_at,
  psr.id as source_ref_id,
  psr.product_id,
  psr.identity_key,
  psr.external_id,
  psr.is_primary,
  psr.last_seen_at,
  psr.updated_at as ref_updated_at
from incoming i
left join public.product_source_refs psr
  on psr.source_type = 'scraper'
 and psr.source_name = i.store_name
 and (
   psr.external_id is not distinct from i.source_id
   or psr.identity_key = (i.store_name || ':' || coalesce(i.source_id, ''))
 )
order by psr.updated_at desc nulls last, psr.created_at desc;
```

### Query 5: latest mediapark source_id=40 in inbox

```sql
select
  event_id,
  store_name,
  source_id,
  payload_hash,
  process_status,
  error_message,
  received_at,
  processed_at,
  created_at
from public.scraper_incoming_events
where store_name = 'mediapark'
  and source_id = '40'
order by created_at desc
limit 20;
```

---

## How To Interpret `process_status` (inbox)

Допустимые значения в check-constraint: **`received`**, **`processed`**, **`duplicate`**, **`failed`**, **`quarantined`**.

| Статус | Смысл |
|--------|--------|
| `processed` | Событие принято, запись в inbox, бизнес-путь (в т.ч. RPC каталога) прошёл, ack |
| `duplicate` | Dedupe по `event_id` или по бизнес-ключу, ack без повторного эффекта |
| `failed` | Ошибка обработки (см. `error_message`), дальше — retry/quarantine по политике consumer |
| `quarantined` | Терминальный исход после ретраев или инвариант / quarantine |
| `received` | Промежуточное (редко видно извне, если не застряло) |

Таблица **`scraper_incoming_rejections`** — только сообщения, **отклонённые до записи в inbox** (невалидный JSON/контракт): смотреть **`validation_error`**.

Отдельного статуса `retryable_failed` в колонке inbox **нет** — ретраи отражаются повторными доставками / очередями и итоговым `failed`/`quarantined`.

---

## Final Stabilization Checklist (CRM)

- Consumer только `crm.products.import.v1`
- Inbox всегда пишется на успешном пути после валидации (дубликаты — отдельная ветка)
- `process_status` обновляется детерминированно
- Terminal invalid → `scraper_incoming_rejections` + `validation_error`
- Retries через `crm.products.retry` (см. код `applyAckDecision` / README модуля)
- Каталог: обновление `product_source_refs.last_seen_at` / строки `products`

---

## Что проверить дальше

Выполнить в Supabase SQL Editor **Query 1–3** (исправленные выше) для `event_id = 36634eb0-f194-5637-ac8e-ca8989255fc6`.

- **Query 1** `processed` или `duplicate` → связка Rabbit → CRM рабочая для этого события.
- **Query 1** пусто, **Query 3** обновлялось в том же окне времени → возможен dedupe другим ключом или сообщение не дошло до inbox (DLQ / другая очередь / consumer не тот).
- **Query 2** не пусто → разбор **`validation_error`**.

---

*Документ синхронизирован со схемой миграций: `20260403160000_scraper_consumer_skeleton.sql`, `20260410180000_scraper_incoming_rejections.sql`, `20260403120000_catalog_v2_foundation.sql` (`product_source_refs`).*
