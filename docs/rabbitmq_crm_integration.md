# Интеграция CRM с RabbitMQ

## Назначение

Актуальный контур доставки в проекте такой:

`spider -> scraper DB -> outbox -> publisher service -> RabbitMQ -> CRM consumer`

Это значит, что CRM больше не должен ждать прямой HTTP-синхронизации от парсера. CRM должен выступать как consumer RabbitMQ, читать событие `scraper.product.scraped.v1`, валидировать его и выполнять idempotent upsert в свою модель данных.

## Что CRM должен подключить

### Базовая топология RabbitMQ

| Параметр | Текущее значение | Назначение |
|---|---|---|
| `exchange` | `moscraper.events` | Основной exchange, куда публикует scraper |
| `exchange_type` | `topic` | Тип exchange |
| `routing_key` | `listing.scraped.v1` | Routing key события товара |
| `event_type` | `scraper.product.scraped.v1` | Тип события внутри сообщения |
| `schema_version` | `1` | Версия JSON-контракта |
| `publication_version` | `1` | Версия publication metadata |

### Какую очередь использовать CRM

Есть 2 варианта:

1. Рекомендуемый production-вариант: CRM создаёт свою очередь, например `crm.products.import.v1`, и bind-ит её к exchange `moscraper.events` по routing key `listing.scraped.v1`.
2. Упрощённый вариант: CRM читает напрямую из `scraper.products.v1`.

Рекомендуется вариант 1, потому что:

- CRM не зависит от внутренней scraper-очереди.
- Можно независимо настраивать retry, DLQ и prefetch.
- Можно подключать несколько downstream-consumer'ов без конфликтов.

## Рекомендуемые настройки CRM

Ниже пример рекомендуемых настроек на стороне CRM:

| Поле | Пример значения | Обязательно | Комментарий |
|---|---|---|---|
| `RABBITMQ_URL` | `amqp://user:password@rabbitmq:5672/vhost` | да | Строка подключения CRM к RabbitMQ |
| `RABBITMQ_EXCHANGE` | `moscraper.events` | да | Exchange scraper-событий |
| `RABBITMQ_EXCHANGE_TYPE` | `topic` | да | Должен совпадать с producer |
| `RABBITMQ_ROUTING_KEY` | `listing.scraped.v1` | да | Фильтр сообщений |
| `CRM_CONSUMER_QUEUE` | `crm.products.import.v1` | да | Собственная очередь CRM |
| `CRM_CONSUMER_PREFETCH` | `20` | да | Ограничение одновременной обработки |
| `CRM_CONSUMER_DLQ` | `crm.products.import.dlq` | желательно | Очередь для невалидных/необрабатываемых сообщений |
| `CRM_CONSUMER_RETRY_EXCHANGE` | `crm.products.retry` | желательно | Отдельный exchange для retry |
| `CRM_CONSUMER_MAX_RETRIES` | `5` | желательно | Лимит повторов на стороне CRM |

## Что приходит в AMQP message

Scraper публикует durable persistent message со следующими AMQP-свойствами:

| AMQP-свойство | Значение |
|---|---|
| `delivery_mode` | `persistent` |
| `content_type` | `application/json` |
| `message_id` | `event_id` |
| `type` | `scraper.product.scraped.v1` |
| `headers.schema_version` | `1` |
| `headers.store_name` | имя магазина, например `mediapark` |
| `headers.scrape_run_id` | id конкретного scraper-run |
| `headers.payload_hash` | бизнес-хэш полезной нагрузки |

CRM может использовать `message_id` и headers для быстрой фильтрации, но источником истины должен оставаться JSON body.

## Формат JSON-сообщения

Тело сообщения приходит как UTF-8 JSON со схемой `shared/contracts/scraper_product_event.schema.json`.

### Верхний уровень события

| JSON-путь | Тип | Обязательно | Описание |
|---|---|---|---|
| `event_id` | `string` | да | Уникальный идентификатор события. Один outbox row = один стабильный `event_id`, даже при retry публикации |
| `event_type` | `string` | да | Сейчас всегда `scraper.product.scraped.v1` |
| `schema_version` | `integer` | да | Версия схемы события. Сейчас `1` |
| `scrape_run_id` | `string` | да | Идентификатор конкретного запуска scraper |
| `store_name` | `string` | да | Магазин-источник: `mediapark`, `texnomart`, `uzum`, `alifshop` и т.д. |
| `source_id` | `string \| null` | нет | Внешний id товара у магазина, если удалось извлечь |
| `source_url` | `string` | да | URL карточки товара |
| `scraped_at` | `string(date-time)` | да | UTC-время фактического парсинга товара |
| `payload_hash` | `string` | да | Бизнес-отпечаток содержимого товара |
| `structured_payload` | `object` | да | Полезная бизнес-нагрузка для CRM |
| `publication` | `object` | да | Служебные метаданные публикации в RabbitMQ |

### Поля `structured_payload`

`structured_payload` - основной блок, который CRM должен использовать для импорта карточки товара.

| JSON-путь | Тип | Обязательно | Как использовать в CRM |
|---|---|---|---|
| `structured_payload.store_name` | `string` | да | Дублирует магазин-источник |
| `structured_payload.source_url` | `string` | да | Хранить как URL источника |
| `structured_payload.source_id` | `string \| null` | нет | Внешний id в магазине, если есть |
| `structured_payload.title` | `string` | да | Название товара |
| `structured_payload.brand` | `string \| null` | нет | Бренд |
| `structured_payload.price_raw` | `string \| null` | нет | Исходная цена как строка. CRM может отдельно парсить numeric-значение, но исходную строку лучше сохранять |
| `structured_payload.in_stock` | `boolean \| null` | нет | Наличие товара |
| `structured_payload.raw_specs` | `object` | да | Сырые характеристики. Набор ключей динамический, порядок не гарантируется |
| `structured_payload.image_urls` | `array[string]` | да | Ссылки на изображения |
| `structured_payload.description` | `string \| null` | нет | Описание товара |
| `structured_payload.category_hint` | `string \| null` | нет | Подсказка категории, если scraper её определил |
| `structured_payload.external_ids` | `object<string,string>` | нет | Внешние id из разных источников |
| `structured_payload.scraped_at` | `string(date-time)` | да | Повтор верхнеуровневого времени парсинга |
| `structured_payload.payload_hash` | `string` | да | Повтор верхнеуровневого `payload_hash` |
| `structured_payload.raw_payload_snapshot` | `object` | да | Фрагмент исходного scraper payload для аудита и диагностики |
| `structured_payload.scrape_run_id` | `string` | да | Повтор `scrape_run_id` |
| `structured_payload.identity_key` | `string` | да | Главный стабильный ключ источника для CRM |

### Что такое `identity_key`

`structured_payload.identity_key` - это лучший ключ для связи товара в CRM с конкретным source-product.

Правило формирования:

- если есть `source_id`, ключ имеет вид `store_name:source_id`, например `mediapark:32771`;
- если `source_id` нет, scraper строит ключ из canonical URL и sha256-хэша.

Из этого следуют 2 важных правила для CRM:

- нельзя предполагать, что `source_id` всегда есть;
- нельзя заново вычислять `identity_key` на стороне CRM, нужно брать готовое значение из сообщения.

### Поля `publication`

Этот блок нужен для диагностики доставки и трассировки. Бизнес-логика CRM не должна зависеть от него.

| JSON-путь | Тип | Обязательно | Комментарий |
|---|---|---|---|
| `publication.publication_version` | `integer` | да | Версия блока publication metadata |
| `publication.exchange_name` | `string \| null` | нет | Exchange, из которого было опубликовано сообщение |
| `publication.queue_name` | `string \| null` | нет | Scraper-side queue. Это не обязательно очередь CRM |
| `publication.routing_key` | `string \| null` | нет | Routing key публикации |
| `publication.outbox_status` | `string` | да | Статус outbox на момент попытки публикации |
| `publication.attempt_number` | `integer` | нет | Номер попытки публикации |
| `publication.publisher_service` | `string \| null` | нет | Имя publisher service |
| `publication.outbox_created_at` | `string(date-time)` | да | Когда outbox row был создан |
| `publication.published_at` | `string(date-time) \| null` | нет | Для реально опубликованного события должен быть заполнен UTC timestamp |

Важно:

- `publication.queue_name` может быть `scraper.products.v1`, даже если CRM читает свою очередь `crm.products.import.v1`;
- текущий runtime публикует событие с final `publication.outbox_status = "published"` и заполненным `publication.published_at`;
- CRM должен рассматривать блок `publication` как observability metadata, а не как часть продукта.

## Обязательные правила обработки на стороне CRM

### 1. Валидировать тип события

CRM должен принимать сообщение только если:

- `content_type = application/json`;
- `event_type = scraper.product.scraped.v1`;
- `schema_version = 1`.

Если пришёл неизвестный `schema_version` или другой `event_type`, сообщение лучше отправить в quarantine/DLQ, а не пытаться обработать "как получится".

### 2. Декодировать JSON и проверить обязательные поля

Минимально обязательные поля для успешного импорта:

- `event_id`
- `event_type`
- `schema_version`
- `scrape_run_id`
- `store_name`
- `source_url`
- `scraped_at`
- `payload_hash`
- `structured_payload.identity_key`
- `structured_payload.title`
- `structured_payload.raw_specs`
- `structured_payload.image_urls`

### 3. Сделать идемпотентность

Нужно реализовать 2 уровня защиты:

1. `event_id`-dedupe
2. business dedupe по `identity_key + payload_hash`

Рекомендуемая логика:

- если `event_id` уже обработан, сообщение можно `ack` без повторного применения;
- если для того же `identity_key` уже сохранён такой же `payload_hash`, можно не перезаписывать карточку повторно;
- если `identity_key` тот же, но `payload_hash` новый, нужно обновить товар в CRM.

### 4. Делать upsert, а не blind insert

Рекомендуемый бизнес-ключ в CRM:

- основной ключ товара источника: `identity_key`
- вспомогательные поля для поиска: `store_name`, `source_id`, `source_url`

Рекомендуемый upsert-сценарий:

1. Найти запись по `identity_key`.
2. Если записи нет, создать новую.
3. Если запись есть и `payload_hash` изменился, обновить поля товара.
4. Сохранить `last_event_id`, `last_payload_hash`, `last_scraped_at`.

### 5. Разделять product-data и delivery-metadata

Для карточки товара CRM должен использовать в первую очередь:

- `structured_payload.title`
- `structured_payload.brand`
- `structured_payload.price_raw`
- `structured_payload.in_stock`
- `structured_payload.raw_specs`
- `structured_payload.image_urls`
- `structured_payload.description`
- `structured_payload.category_hint`
- `structured_payload.external_ids`

Для аудита и трассировки CRM должен отдельно сохранять:

- `event_id`
- `scrape_run_id`
- `payload_hash`
- `publication.*`
- полный `raw_event_json`

## Рекомендуемая схема хранения в CRM

Ниже не обязательная, но практичная модель таблиц.

### Таблица 1: входящие события

Например `crm_incoming_scraper_events`.

| Поле CRM | Тип | Назначение |
|---|---|---|
| `event_id` | string, unique | Защита от повторной обработки |
| `event_type` | string | Тип события |
| `schema_version` | int | Версия контракта |
| `store_name` | string | Источник |
| `source_id` | string nullable | Внешний id |
| `source_url` | string | URL карточки |
| `identity_key` | string | Стабильный ключ товара источника |
| `payload_hash` | string | Бизнес-хэш состояния |
| `scrape_run_id` | string | Привязка к scraper run |
| `scraped_at` | datetime UTC | Когда scraper увидел карточку |
| `received_at` | datetime UTC | Когда CRM получил сообщение |
| `processed_at` | datetime UTC nullable | Когда CRM обработал сообщение |
| `process_status` | string | `received`, `processed`, `duplicate`, `failed`, `quarantined` |
| `error_message` | text nullable | Текст ошибки обработки |
| `raw_event_json` | json/text | Полная копия входящего события |

### Таблица 2: актуальное состояние source-product

Например `crm_source_products`.

| Поле CRM | Тип | Назначение |
|---|---|---|
| `identity_key` | string, unique | Главный внешний ключ |
| `store_name` | string | Магазин |
| `source_id` | string nullable | Внешний id товара |
| `source_url` | string | URL товара |
| `title` | string | Название |
| `brand` | string nullable | Бренд |
| `price_raw` | string nullable | Исходная цена |
| `in_stock` | boolean nullable | Наличие |
| `description` | text nullable | Описание |
| `category_hint` | string nullable | Подсказка категории |
| `raw_specs_json` | json/text | Характеристики |
| `image_urls_json` | json/text | Изображения |
| `external_ids_json` | json/text | Внешние ids |
| `last_payload_hash` | string | Последний применённый payload |
| `last_event_id` | string | Последнее событие |
| `last_scrape_run_id` | string | Последний run |
| `last_scraped_at` | datetime UTC | Последнее scraper-время |
| `updated_at` | datetime UTC | Время обновления в CRM |

## Правила `ack` / `nack`

| Ситуация | Действие CRM |
|---|---|
| Сообщение успешно сохранено и применено | `ack` |
| `event_id` уже был обработан | `ack` |
| `identity_key + payload_hash` уже применены | `ack` |
| Временная ошибка БД / сетевой зависимости CRM | `nack` или retry через retry-queue |
| JSON битый или нет обязательных полей | `reject` без requeue, затем в DLQ/quarantine |
| Неизвестный `schema_version` | `reject` без requeue, затем в quarantine |
| Неизвестный `event_type` | `reject` без requeue, затем в quarantine |

Не стоит бесконечно requeue-ить невалидные сообщения, иначе CRM сам себе создаст бесконечный цикл.

## Пошаговый алгоритм consumer-а CRM

1. Подключиться к RabbitMQ по `RABBITMQ_URL`.
2. Убедиться, что есть bind очереди CRM к `moscraper.events` по `listing.scraped.v1`.
3. Установить `prefetch`, например 10-20.
4. Получить сообщение.
5. Проверить AMQP `content_type`, `message_id`, `type`.
6. Распарсить JSON body.
7. Провалидировать обязательные поля.
8. Проверить, не обработан ли уже `event_id`.
9. Извлечь `identity_key = structured_payload.identity_key`.
10. Проверить, совпадает ли `payload_hash` с уже сохранённым состоянием.
11. Выполнить upsert карточки товара.
12. Сохранить audit-запись входящего события.
13. Отправить `ack`.

## Что CRM не должен делать

- Не пересчитывать `payload_hash` для принятия решения об обработке. Нужно использовать значение от producer.
- Не пересчитывать `identity_key`.
- Не строить бизнес-логику на `publication.outbox_status`.
- Не предполагать, что `source_id` всегда заполнен.
- Не предполагать, что `raw_specs` имеет фиксированный набор ключей.
- Не завязываться на конкретный порядок ключей в JSON.

## Минимальный контракт для первой версии интеграции

Если нужно сделать быстрый рабочий consumer, достаточно поддержать такой обязательный минимум:

- подключение к exchange `moscraper.events`;
- bind по `listing.scraped.v1`;
- чтение JSON body;
- проверка `event_type = scraper.product.scraped.v1`;
- сохранение `event_id`;
- upsert по `structured_payload.identity_key`;
- сравнение и хранение `payload_hash`;
- сохранение `title`, `price_raw`, `in_stock`, `raw_specs`, `image_urls`, `source_url`;
- `ack` только после успешной записи в CRM.

## Проверка интеграции

Для локальной проверки можно использовать такой сценарий:

1. Поднять RabbitMQ.
2. Запустить scraper на 1 товар.
3. Запустить publisher service.
4. Убедиться, что CRM queue получила сообщение.
5. Проверить, что CRM:
   - сохранил `event_id`;
   - сохранил `identity_key`;
   - создал или обновил товар;
   - не дублирует запись при повторной доставке того же события.

Команды проекта для генерации события:

```powershell
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=1
python -m services.publisher.main --once
```

## Источники истины в репозитории

При расхождениях ориентироваться в таком порядке:

1. `services/publisher/rabbit_publisher.py`
2. `services/publisher/publication_worker.py`
3. `domain/publication_event.py`
4. `shared/contracts/scraper_product_event.schema.json`
5. `infra/rabbitmq/topology.json`

## Короткое резюме для CRM-команды

CRM должен читать событие `scraper.product.scraped.v1` из RabbitMQ, использовать `structured_payload.identity_key` как главный внешний ключ товара, использовать `payload_hash` для защиты от повторного применения одного и того же состояния и делать `ack` только после успешного idempotent upsert в свою БД.
