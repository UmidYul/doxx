# План миграции Moscraper на новый флоу

**Использован коннектор:** GitHub.

**Резюме:** В этом документе представлен подробный поэтапный план перепроектирования текущего репозитория скраппера (Moscraper) к архитектуре «Scraper → RabbitMQ → CRM». Основные цели: убрать все компоненты локального хранения данных (Postgres/Supabase, Celery/Redis, таблицы `parse_cache`/`pending_events`), реализовать публикацию событий в очередь RabbitMQ (с помощью **aio-pika**, CloudEvents, Pydantic v2, orjson) и полностью обновить документацию под новый flow. План разбит на разделы проекта (модели, бизнес-логика, па́йплайны, па́йплайны, инфраструктуру и т.д.), в каждом — на мини-итерации (3–6 шагов) с подробными задачами и готовыми промптами на русском. Каждый промпт ссылается на «документ миграции» как источник истины и подчёркивает отсутствие хранилища в скраппере.


```mermaid
flowchart LR
    Spider[Scraper (Spiders)] -->|публикует| MQ[RabbitMQ]
    MQ --> CRM[CRM (владеет данными)]
    Spider -.->|отдаёт Item| PublishPipeline
    PublishPipeline -->|CloudEvent| MQ
    CRM ---|обрабатывает события| Email[CRM Process]
```

## 1. Domain (модели)

**Итерация 1.1:** **Удалить поля CRM/parse_cache из моделей.**  
- **Цель:** В Pydantic-моделях `RawProduct`, `NormalizedProduct`, `events.py` убрать всё, что связано с локальной БД (поля `crm_listing_id`, `crm_product_id`, `id` в событиях, `raw_html`, `parse_logs` и т.д.), так как в stateless-скраппере этого не должно быть【13†L154-L163】【13†L187-L196】.  
- **Приёмка:** Код компилируется без ошибок; `mypy`/flake8 не жалуются на несуществующие поля; нигде в коде нет обращений к Supabase или Postgres.  
- **Файлы:** `domain/events.py`, `domain/normalized_product.py`, `domain/raw_product.py`.  
- **Проверка:** Запустить `pytest` и `mypy`; убедиться, что новые модели сериализуются в JSON без лишних полей.  
- **Промпт (рус.):**  
  ```
  Согласно документу миграции (moscraper_migration_pack.md), обнови модели в папке domain: убери поля crm_listing_id, crm_product_id, id-ы, а также raw_html и другие, связанные с локальным хранилищем. Параметры событий должны включать только данные из парсинга (source, source_id, title, price и т.п.). Укажи, что теперь скраппер НЕ хранит локально результаты и передает всё в очередь. 
  ```
- **Пример:** после изменений модель события может выглядеть так: `ProductFoundEvent(source: str, source_id: str, title: str, price: float, in_stock: bool)`.

**Итерация 1.2:** **Создать модель сообщения CloudEvent.**  
- **Цель:** Добавить в `domain/` новую Pydantic-модель (например, `CloudEvent`), соответствующую спецификации CloudEvents (поля `specversion`, `type`, `source`, `id`, `time`, `data`, `datacontenttype`)【4†L78-L86】. Поле `data` — вложенная модель с данными товара (например, скраммарим из `NormalizedProduct`). Генерировать `id` через `uuid4()`, `time` — текущее UTC. Определить `type` как имя события (напр. `"com.uztechscraper.product.found.v1"`).  
- **Приёмка:** Pydantic-модель компилируется и при сериализации возвращает JSON по формату CloudEvents. Поле `data` валидируется по вложенной схеме.  
- **Файлы:** создать `domain/message.py` (CloudEvent, ProductData и т.д.).  
- **Проверка:** Написать быстрый REPL: создаём `CloudEvent(type="...", data=ProductData(...))`, вызываем `orjson.dumps()`, смотрим структуру JSON.  
- **Промпт (рус.):**  
  ```
  Добавь Pydantic-модель CloudEvent в domain/message.py по спецификации CloudEvents v1.0: поля specversion (="1.0"), type (имя события), source (идентификатор скраппера), id (UUID), time (timestamp UTC), datacontenttype="application/json", data (вложенный объект с полями товара: source, source_id, title, price, in_stock, raw_specs, image_urls). ID и время генерируй автоматически. Документально: каждое событие должно быть валидируемым JSON по CloudEvents (с помощью pydantic v2 и orjson). 
  ```

  *Пример кода (pydantic v2):*
  ```python
  from pydantic import BaseModel, Field
  from uuid import uuid4
  from datetime import datetime

  class ProductData(BaseModel):
      source: str
      source_id: str | None = None
      title: str
      price: float
      in_stock: bool
      raw_specs: dict[str, str] = {}
      image_urls: list[str] = []

  class CloudEvent(BaseModel):
      specversion: str = "1.0"
      type: str
      source: str
      id: str = Field(default_factory=lambda: str(uuid4()))
      time: datetime = Field(default_factory=datetime.utcnow)
      datacontenttype: str = "application/json"
      data: ProductData
  ```
  Этот пример — лишь иллюстрация формата; его не нужно копировать дословно.

**Итерация 1.3:** **Удалить необязательный `raw_html`.**  
- **Цель:** Убрать поле `raw_html` у всех моделей (если оно осталось в `RawProduct` или таблицах). Парсер больше не хранит полной HTML.  
- **Приёмка:** Модели работают без поля; не возникало KeyError при доступе к item['raw_html'].  
- **Файлы:** `domain/raw_product.py`, миграции/настройки (если есть).  
- **Проверка:** Убедиться, что собранные `RawProduct` items не содержат `raw_html`.  
- **Промпт (рус.):**  
  ```
  Убери поле raw_html из всех моделей и таблиц, так как мы больше не храним скачанный HTML. Обеспечь, чтобы код работал без этого поля и не падал при его отсутствии. 
  ```

## 2. Application (бизнес-логика)

**Итерация 2.1:** **Удалить DeltaDetector и parse_cache.**  
- **Цель:** Избавиться от механизма сравнения с локальным кэшем. Удалить весь файл `application/delta_detector.py` и ссылки на него. Логика `parse_cache` больше не нужна【13†L185-L194】.  
- **Приёмка:** Удалены импорты/использование `DeltaDetector`. Код разборки (`parse_orchestrator`) запускается без `delta_detector`.  
- **Файлы:** `application/delta_detector.py` (удалить), `application/parse_orchestrator.py` (удалить вызовы delta_detector).  
- **Проверка:** Убедиться, что больше нет обращений к таблице `parse_cache`. Все парсеры всегда «публикуют всё», без фильтрации.  
- **Промпт (рус.):**  
  ```
  Удали из кода весь DeltaDetector (файл delta_detector.py и его вызовы). Согласно документу миграции, скраппер больше не сравнивает данные с локальным кэшем, он сразу отправляет всё в очередь. Проверь, что нигде не осталось упоминаний parse_cache или функций сравнения. 
  ```

**Итерация 2.2:** **Заменить event_sender на публикацию в RabbitMQ.**  
- **Цель:** Удалить модули `application/crm_client.py` и `application/event_sender.py`. Вместо REST API-вызывов к CRM внедрить асинхронную публикацию через **PublishPipeline** (см. разрыв труб). Перейти на библиотеку `aio-pika`. Обеспечить подтверждение публикации (publisher confirms) и логирование ошибок.  
- **Приёмка:** Убраны зависимости `httpx`/`requests`. Фактически нет сетевых вызовов в этих модулях. Новая логика — одна функция publish() с логгированием.  
- **Файлы:** удалить `application/crm_client.py`, `application/event_sender.py`. Добавить зависимость `aio-pika`.  
- **Проверка:** Убедиться, что ни один тест или код не вызывает `send_to_crm` или `EventSender`. Для наглядности можно написать макет вызова PublishPipeline и проверить, что сообщения уходят в очередь.  
- **Промпт (рус.):**  
  ```
  Удали файлы crm_client.py и event_sender.py. Теперь вместо синхронной отправки в CRM используй PublishPipeline (aio-pika). Укажи, что PublishPipeline будет асинхронно публиковать события, и что в коде больше нет HTTP-запросов к CRM. Добавь логи при ошибках публикации (и, при желании, ретраи). 
  ```

**Итерация 2.3:** **Упростить ParseOrchestrator.**  
- **Цель:** Избавиться от сложных режимов discover/queue. Оставить один цикл запуска паутин, например `full_parse`, который сразу обходит все нужные URL. Убрать интеграцию с Celery (`tasks/parse_tasks.py`).  
- **Приёмка:** Методы `fast_parse`, `full_parse`, `discover` становятся простыми вызовами Scrapy (без Celery). Разбор происходит последовательно в рамках одного процесса.  
- **Файлы:** `application/parse_orchestrator.py`, `tasks/parse_tasks.py`.  
- **Проверка:** `full_parse` успешно выполняет заданный спайдер (например, scrapy crawl), нет ошибок при отсутствии Celery/parse_queue.  
- **Промпт (рус.):**  
  ```
  Перепиши ParseOrchestrator: убери все упоминания Celery и parse_queue. Пусть full_parse просто вызывает scrapy crawl нужного spider, а discover удален. Fast_parse можно убрать или адаптировать как облегченную версию. В итоге не должно быть внешнего планировщика или очереди между итерациями — скраппер сам запускает и ждёт результатов. 
  ```

**Итерация 2.4:** **Отключить LLM и расширенные извлечения.**  
- **Цель:** В `application/extractors` убрать или заморозить код, который вызывает LLM (Claude и ему подобные). Полностью отключить `application/extractors/llm_extractor.py` и не вызывать его из `spec_extractor.py`.  
- **Приёмка:** В `SpecExtractor` используется только structured (табличные) извлечения и простая regex-обработка; не делается API-запросов к LLM.  
- **Файлы:** `application/extractors/spec_extractor.py`, `application/extractors/llm_extractor.py`.  
- **Проверка:** Собрать скраппер без ошибок; запустить один из spiders и убедиться, что он не обращается к LLM/Redis.  
- **Промпт (рус.):**  
  ```
  Убери все LLM-вызовы из пайплайна извлечения спецификаций (SpecExtractor). Он должен использовать только структурные парсеры и регулярные выражения. Укажи, что дальнейшую семантику CRM сделает на своей стороне. Проверь, что код не использует anthropic/redis для доп. обработки. 
  ```

## 3. Spiders (парсеры магазинов)

**Итерация 3.1:** **Избавиться от Celery в спайдерах.**  
- **Цель:** Спайдеры запускаются обычным `scrapy crawl` вместо Celery. Удалить любые импорты `tasks.parse_tasks` и `tasks.celery_app`.  
- **Приёмка:** В каталоге `tasks/` нет кода, который передавал бы задачи спайдерам (в частности, `celery_app.py`, `parse_tasks.py`). В процессе разработки скрипт запускается через CLI.  
- **Файлы:** `tasks/celery_app.py`, `tasks/parse_tasks.py`.  
- **Проверка:** Удостовериться, что никто не вызывает `celery_app` из кода, и что расписание jobs вынесено в документацию.  
- **Промпт (рус.):**  
  ```
  Убери использование Celery в спайдерах. Удалить завязки на tasks.parse_tasks, celery_app. Спайдеры должны запускаться как scrapy crawl, без broker. 
  ```

**Итерация 3.2:** **Проверить логику `start_requests`/`parse`.**  
- **Цель:** Убедиться, что ни один Spider не пытается напрямую записать в БД или обработать данные иначе. Каждый spider должен отдавать Python-словарь (Item), а далее данные обрабатываются через пайплайны.  
- **Приёмка:** Все `infrastructure/spiders/*.py` возвращают объекты `RawProduct` и переходят к следующему URL, не делают INSERT/UPDATE в БД.  
- **Файлы:** `infrastructure/spiders/*.py`.  
- **Проверка:** Запустить пример spider (например, `scrapy crawl mediapark`) на тестовой странице и посмотреть лог: он должен только печатать или сохранять items, не падать на непроходах.  
- **Промпт (рус.):**  
  ```
  Проверь, что все спайдеры возвращают Item (словарь) и не пытаются сохранять данные самостоятельно. Если где-то есть вызов `supabase_client` или `session.execute`, убери его. Пара убедится, что каждый Spider завершает работу, не бросая ошибок из-за отсутствующих БД. 
  ```

## 4. Pipelines (обработка Item)

**Итерация 4.1:** **Упростить NormalizePipeline.**  
- **Цель:** В `infrastructure/pipelines/normalize_pipeline.py` убрать «тяжёлые» стадии (Regex и LLM). Оставить только базовую нормализацию: очистка цены/бренда (`normalize_price`, `normalize_brand`), проверку типов и подготовку структуры данных. Если нужно сгруппировать характеристики, можно использовать простые правила или передавать `raw_specs` дальше.  
- **Приёмка:** При парсинге `RawProduct` метод `process_item` возвращает корректный `NormalizedProduct` без вызова `extract_specs`. Тестовые объекты (`RawProduct`) преобразуются в модели с простыми полями (float для цены, bool для наличия, dict для характеристик).  
- **Файлы:** `infrastructure/pipelines/normalize_pipeline.py`.  
- **Проверка:** Запустить unit-тест: подать `RawProduct` c простыми полями и убедиться, что на выходе получается ожидаемый JSON (например, `{"price": 1234.5, "currency": "UZS", "in_stock": true}`).  
- **Промпт (рус.):**  
  ```
  Сделай NormalizePipeline легковесным: теперь он только конвертирует строки цен в числа, обрезает знаки валюты, нормализует True/False и фильтрует лишние поля. Не вызывай extract_specs и LLM. Например, если цена = "1 234 000", преврати в float 1234000.0. В документации отметить, что полный анализ характеристик перейдёт в CRM. 
  ```

**Итерация 4.2:** **Удалить ImagePipeline.**  
- **Цель:** В `infrastructure/pipelines/image_pipeline.py` убрать обработку изображений: не скачивать и не анализировать (CLIP, rembg). Пусть spider просто собирает `image_urls`, а в дальнейшем CRM будет их загружать и классифицировать.  
- **Приёмка:** Файл `image_pipeline.py` может быть удалён или превращён в no-op. Остальные пайплайны работают корректно, `image_urls` остаются в item без изменений.  
- **Файлы:** `infrastructure/pipelines/image_pipeline.py`, убрать из `config/scrapy_settings.py`.  
- **Проверка:** Собрать и запустить скраппер, убедиться, что `NormalizedProduct.image_urls` содержит список URL без ранжирования, и никаких ошибок CLIP/rembg нет.  
- **Промпт (рус.):**  
  ```
  Удали или закомментируй код в ImagePipeline. Укажи, что мы больше не анализируем картинки на этапе скрапа. Пусть просто передаются списки image_urls. Убери зависимости rembg, torch, PIL и т.д. 
  ```

**Итерация 4.3:** **Удалить DeltaPipeline.**  
- **Цель:** Убрать `infrastructure/pipelines/delta_pipeline.py` вместе со всей логикой upsert в таблицы магазинов и генерацией событий. Вместо него используем **PublishPipeline** (ниже).  
- **Приёмка:** В `config/scrapy_settings.py` удалена строка для DeltaPipeline. Файл `delta_pipeline.py` удалён.  
- **Файлы:** `infrastructure/pipelines/delta_pipeline.py` (удалить), `config/scrapy_settings.py` (удалить ссылку).  
- **Проверка:** Убедиться, что собранный `scrapy crawl` завершает обработку без ошибок после нормализации, и нет упоминаний `delta_pipeline`.  
- **Промпт (рус.):**  Также сам основной функционал, саму идею, то есть скраппинга, мы должны улучшить. То есть весь функционал скраппинга, или же парсинга, по-другому, должен работать идеально, полностью. Он должен быть готовым парсить любой вид страниц и получать максимальные полезные данные с этих страниц.
  ```
  Удали файл DeltaPipeline и его упоминание в настройках. Это удалит всю логику сравнения с кэшем и отправки дельта-событий через REST. 
  ```

**Итерация 4.4:** **Добавить PublishPipeline (RabbitMQ).**  
- **Цель:** Написать новый пайплайн `infrastructure/pipelines/publish_pipeline.py`, который будет асинхронно публиковать события в RabbitMQ (обменник, например, типа fanout, без ключа). Использовать `aio-pika` с `publisher_confirms=True` для гарантии доставки. Сериализовать объект CloudEvent через `orjson.dumps()`. Добавить логирование успеха/ошибок.  
- **Приёмка:** В `scrapy_settings.py` в `ITEM_PIPELINES` добавлен `PublishPipeline`. В процессе сборки `PublishPipeline.process_item` вызывается и отправляет сообщение в очередь. При отключённом RabbitMQ парсер выдаёт понятную ошибку (ConnectionError).  
- **Файлы:** создать `infrastructure/pipelines/publish_pipeline.py`, изменить `config/scrapy_settings.py`.  
- **Проверка:** Написать модульный тест: мокать соединение `aio-pika`, проверить, что `publish` вызывается с правильно сериализованным JSON (orjson), и при исключении генерируется лог с retry-декоратором (если добавлен). Также вручную поднять RabbitMQ, запустить spider и убедиться, что сообщения появляются в очереди.  
- **Промпт (рус.):**  
  ```
  Реализуй PublishPipeline: при открытии соединяется к RabbitMQ (aio_pika.connect_robust) с подтверждениями. В process_item публикатор отправляет объект CloudEvent (из 1.2) в exchange, используя orjson.dumps. Настрой publisher_confirms=True. Если публикация не прошла, логируй ошибку и давай разумный retry/backoff. Укажи, что в итоге все данные будут публиковаться в очередь, а логи ключевых шагов будут выводиться. 
  ```  
  *Пример кода (без привязки к репо):*  
  ```python
  import aio_pika, orjson
  from cloudevents.sdk import v1  # или аналог
  class PublishPipeline:
      async def open_spider(self, spider):
          connection = await aio_pika.connect_robust(RABBITMQ_URL)
          self.channel = await connection.channel(publisher_confirms=True)
          self.exchange = await self.channel.declare_exchange("events", aio_pika.ExchangeType.FANOUT)
      async def process_item(self, item, spider):
          cloud_event = CloudEvent(type="com.uztechscraper.product", source=spider.store_name, data=item._normalized)
          body = orjson.dumps(cloud_event.model_dump())  # pydantic -> dict -> bytes
          await self.exchange.publish(aio_pika.Message(body=body, content_type="application/json"), routing_key="")
          return item
      async def close_spider(self, spider):
          await self.channel.close()
  ```
  Эта схема использует publisher_confirms и не задерживает спайдер (await внутри асинхронного пайплайна).

## 5. Middlewares

**Итерация 5.1:** **Переход к `scrapy-playwright` (опционально).**  
- **Цель:** Оставить поддержку Playwright только для нужных сайтов (спайдеры типа UZUM), а в остальных случаях использовать обычный HTTP-запрос. Это уменьшает нагрузку на скраппер.  
- **Приёмка:** В `scrapy_settings.py` `playwright_driver` и middleware настроены, но только `uzum.py` реально запрашивает `playwright`. Остальные спайдеры работают по TCP.  
- **Файлы:** `config/scrapy_settings.py`, `infrastructure/spiders/uzum.py`.  
- **Проверка:** Запустить `scrapy crawl uzum` и убедиться, что он использует Playwright. Запустить `mediapark` — он должен идти обычным способом.  
- **Промпт (рус.):**  
  ```
  Убедись, что scrapy-playwright используется только там, где нужно (например, в Spider для UZUM). В scrapy_settings.yml настрой middleware так, чтобы по умолчанию playwright не включался. Добавь флаг или условие в Spiders, чтобы включать его выборочно. 
  ```

**Итерация 5.2:** **Удалить Redis/BloomFilter из retry/limit.**  
- **Цель:** Проверить middlewares (`ratelimit`, `retry`) на наличие кода Redis или BloomFilter (использовался для снижения дубликатов). Удалить эти зависимости, чтобы мидлвары были простыми.  
- **Приёмка:** Нет `import redis` или BloomFilter в мидлварах. Rate limiting и retry делают паузу или повтор попытки в текущем процессе.  
- **Файлы:** `infrastructure/middlewares/*.py`.  
- **Проверка:** Убедиться, что записи в Redis и bloom-фильтры больше не используются (grep по репозиторию), и что при частых ошибках реквестов скраппер корректно делает паузы.  
- **Промпт (рус.):**  
  ```
  Проверь, что в middleware нет зависимостей от Redis или BloomFilter. Если где-то встречается redis, удали этот код. Убедись, что мидлвары работают корректно без внешнего кеша. 
  ```

## 6. Инфраструктура БД

**Итерация 6.1:** **Удалить папку `infrastructure/db`.**  
- **Цель:** Полностью убрать всё, что касается Supabase/Postgres: репозитории, миграции, модели `records.py`, сессии и т.д. Структура `infrastructure/db` более не нужна.  
- **Приёмка:** Каталог `infrastructure/db` отсутствует. В `pyproject.toml` удалены `supabase`, `psycopg2-binary` и пр. Нет упоминаний `get_supabase()` в коде.  
- **Файлы:** `infrastructure/db/*` (удалить всё).  
- **Проверка:** Провести `grep -R supabase .` и убедиться, что ничего не найдено.  
- **Промпт (рус.):**  
  ```
  Удали весь каталог infrastructure/db и связанные файлы. Укажи, что больше не используем Supabase/Postgres, а данные идут сразу в очередь. Убери миграции и зависимости supabase-py, psycopg2. 
  ```

**Итерация 6.2:** **Удалить Celery/Redis задачи.**  
- **Цель:** Удалить остатки Celery: файлы `tasks/celery_app.py`, `event_tasks.py`. Также убрать пакеты `celery`, `redis` из зависимостей.  
- **Приёмка:** Нет папки `tasks` (кроме CI/testов). В коде не используется `celery_app`. Зависимость celery убрана.  
- **Файлы:** `tasks/` (удалить папку), `pyproject.toml`.  
- **Проверка:** `pip install .` не устанавливает Celery. Код запускается без `celery`.  
- **Промпт (рус.):**  
  ```
  Удали все упоминания Celery и Redis. Папка tasks теперь не нужна. Сообщи, что планирование запуска парсинга будет внешним (cron или CI). 
  ```

## 7. Конфигурация

**Итерация 7.1:** **Обновить `settings.py`.**  
- **Цель:** Удалить все параметры, связанные с БД или очередями Celery (`SUPABASE_*`, `DATABASE_URL_*`, `REDIS_URL`, `CELERY_*`, `CRM_API_URL`). Добавить параметры RabbitMQ (`RABBITMQ_URL`, `RABBITMQ_EXCHANGE`). Убедиться, что Pydantic Settings всё ещё валидируется.  
- **Приёмка:** В `config/settings.py` остались только: `RABBITMQ_URL`, `RABBITMQ_EXCHANGE`, `MAX_RETRIES` (для публикации), `SENTRY_DSN` и т.д. Переменные окружения `.env` больше не содержат DB.  
- **Файлы:** `config/settings.py`, `.env.example`.  
- **Проверка:** `Settings()` загружается без ошибок при новом `.env.example`.  
- **Промпт (рус.):**  
  ```
  В config/settings.py убери настройки БД и Celery. Добавь RABBITMQ_URL и имя обмена (RABBITMQ_EXCHANGE). Укажи, что приложение достаёт эти параметры из окружения (dotenv). 
  ```

**Итерация 7.2:** **Обновить `scrapy_settings.py`.**  
- **Цель:** В `config/scrapy_settings.py` настроить пайплайны и middleware для нового потока: `ITEM_PIPELINES` должен содержать только Validate, Normalize, PublishPipeline. Убрать `DeltaPipeline` и `ImagePipeline`. Проверить, что `DOWNLOAD_HANDLERS` для Playwright и скопированные настройки остались.  
- **Приёмка:** В `scrapy_settings.py`:  
  - `ITEM_PIPELINES` = { ValidatePipeline:100, NormalizePipeline:200, PublishPipeline:300 }.  
  - Нет `delta_pipeline`, `image_pipeline`.  
  - Middleware (Stealth, Retry, Playwright) остались на своих местах.  
- **Файлы:** `config/scrapy_settings.py`.  
- **Проверка:** `scrapy list` показывает спайдеры; `scrapy crawl mediapark` не падает из-за неверного пайплайна.  
- **Промпт (рус.):**  
  ```
  Перепиши scrapy_settings.py: убери старые пайплайны (delta, image) из ITEM_PIPELINES, добавь PublishPipeline с высоким приоритетом. Проверь правильные порядок пайплайнов (validate, normalize, publish). Удостоверься, что остальные настройки (middlewares, PLAYER) корректны. 
  ```

**Итерация 7.3:** **Убрать дублирование `.env.example`.**  
- **Цель:** Оставить только один шаблон конфигов — `.env.example`. Перенести в него все необходимые переменные (`RABBITMQ_URL`, `RABBITMQ_EXCHANGE`, `SENTRY_DSN` и т.д.). Удалить `env.example` или пометить устаревшим.  
- **Приёмка:** Есть только `.env.example` с актуальными переменными.  
- **Файлы:** `.env.example` (обновить), `env.example` (удалить или игнорировать).  
- **Проверка:** При запуске `Settings()` приложение читает `.env` по стандарту.  
- **Промпт (рус.):**  
  ```
  Оставь единый файл .env.example. Перепиши его, включи туда RABBITMQ_URL, EXCHANGE и прочие новые параметры. Удали или закомментируй второй env.example. 
  ```

**Итерация 7.4:** **Обновить `docker-compose.yml`.**  
- **Цель:** Удалить сервисы PostgreSQL/Redis/Adminer, добавить сервис RabbitMQ. Docker Compose теперь поднимает только два: `rabbitmq` и `scraper` (или схожее). Обеспечить сопоставление портов и переменных окружения для подключения.  
- **Приёмка:** `docker-compose.yml` содержит только настройки для `rabbitmq` (образ `rabbitmq:3-management`) и для сервиса запуска скрапера (например, сборка образа и команда `scrapy crawl`).  
- **Файлы:** `docker-compose.yml`.  
- **Проверка:** Запустить `docker-compose up`, убедиться, что поднялись только rabbitmq и scraper.  
- **Промпт (рус.):**  
  ```
  Перепиши docker-compose.yml: оставь только сервисы rabbitmq (с management UI) и scraper. Удали postgres, redis, adminer. Настрой порты 5672 и 15672 для RabbitMQ. Укажи команду запуска скрапера (scrapy crawl), задав необходимые env-переменные. 
  ```

## 8. Задачи и Celery

**Итерация 8.1:** **Удалить планирование и задачу ретраев.**  
- **Цель:** После удаления `tasks/` и Celery описать, что планирование (cron, GitHub Actions и т.п.) вне кода. Подчеркнуть, что компонент обмена сообщениями (RabbitMQ) берёт на себя надёжность с помощью DLQ/ретраев (в CRM).  
- **Приёмка:** В проекте не осталось кода периодических задач. Документация и Prompts отражают внешнее расписание.  
- **Файлы:** (см. итерации 6.2/7.4).  
- **Проверка:** Отдельных скриптов-демонов нет.  
- **Промпт (рус.):**  
  ```
  Сообщи, что Celery больше не используется: задачи cron будут описаны вне приложения. Напомни, что за надёжность передачи теперь отвечает RabbitMQ (достигать at-least-once). 
  ```

## 9. Документация

**Итерация 9.1:** **Переписать `PROJECT.md`.**  
- **Цель:** Полностью обновить описание архи. Сильно уменьшить упоминания о своей БД и delta-sync【13†L153-L162】. Описать роль скраппера: сразу публиковать `CloudEvent` в очередь. В блок-схеме заменить стрелки «в БД парсера» на «в очередь RabbitMQ». Описать ключевые компоненты (Spiders, базовая нормализация, PublishPipeline).  
- **Приёмка:** `PROJECT.md` отражает новый дизайн. Нет текста «parse_cache»/«pending_events». Есть объяснение, что парсер отдаёт данные и больше ничего не хранит.  
- **Файлы:** `PROJECT.md`.  
- **Проверка:** Проверить, что раздел «4. База данных парсера» (или подобный) описывает отсутствие локального хранилища. Удалить упоминания `alembic`, Supabase.  
- **Промпт (рус.):**  
  ```
  Обнови PROJECT.md: опиши новый поток работы скраппера. Упомяни, что он **не хранит** данные локально, а сразу шлёт события в RabbitMQ (CloudEvents). Убери все объяснения про Alembic, parse_cache, местную БД. Добавь диаграмму Spider → RabbitMQ → CRM, если её там нет. 
  ```

**Итерация 9.2:** **Переписать `BUILD_PLAN.md`.**  
- **Цель:** Актуализировать описание этапов генерации кода (foundation prompt и итерации). Удалить части про Supabase, PostgreSQL, Celery, REST API. Вместо них описать этапы для `PublishPipeline`, настройки RabbitMQ.  
- **Приёмка:** Файл с планом теперь ориентирован на новый flow. Старые пункты (таблицы парсера, event_sender) заменены на пункты про очередь.  
- **Файлы:** `BUILD_PLAN.md`.  
- **Проверка:** Прочитать Foundation prompt: должны быть слова «RabbitMQ», «публикация», «CloudEvent», а не «сохраняем в parse_cache».  
- **Промпт (рус.):**  
  ```
  Исправь BUILD_PLAN.md: в FOUNDATION PROMPT убери упоминания Supabase/постгреса/Sync API. Добавь указание использовать RabbitMQ и описать новый PublishPipeline. В инструкциях для каждого шага убери всё, что связано с parse_cache или Celery, и добавь шаги по настройке очереди. 
  ```

**Итерация 9.3:** **Обновить `.cursorrules` и `.mdc`.**  
- **Цель:** В файлах `.cursorrules` и `scraper.mdc` убрать правила/описания про локальные таблицы. В `.cursorrules` чётко прописать новые правила: **скраппер статeless**, публикует события, CRM хранит данные.  
- **Приёмка:** Нет строк «parse_cache», «pending_events», «POST /parser/sync». В `.cursorrules` добавлено правило «очередь вместо хранилища».  
- **Файлы:** `.cursorrules`, `scraper.mdc`.  
- **Проверка:** Убедиться, что ветка `issue/main` этого репозитория (или файл) содержит только актуальную информацию без противоречий.  
- **Промпт (рус.):**  
  ```
  Перепиши .cursorrules: удали правила о parse_cache и pending_events, добавь правило, что данные идут только в очередь. В scraper.mdc опиши, что парсер публикует события, а CRM их обрабатывает. 
  ```

**Итерация 9.4:** **Обновить `.env.example` и `docker-compose.yml`.**  
- **Цель:** Проверить, что примеры конфигов отражают только новое окружение. В `.env.example` должны быть только переменные RabbitMQ/раб/ORM; в `docker-compose` — только скраппер и rabbitmq.  
- **Приёмка:** `.env.example` содержит `RABBITMQ_URL`, `EXCHANGE`, `SENTRY_DSN` и т.д. Docker Compose без postgres/redis.  
- **Файлы:** `.env.example`, `docker-compose.yml`.  
- **Проверка:** Собрать документацию проекта; ссылки на примеры окружения и compose должны вести к актуальным файлам.  
- **Промпт (рус.):**  
  ```
  Убедись, что .env.example содержит лишь новые настройки (RabbitMQ_URL, Exchange и пр.), а docker-compose.yml поднимает только RabbitMQ и приложение. Если в документации где-то есть старые env-переменные, замени их. 
  ```

## 10. CI/Tests

**Итерация 10.1:** **Юнит-тест для PublishPipeline.**  
- **Цель:** Написать unit-тест для `PublishPipeline`, используя мок `aio-pika`. Проверить, что метод `process_item` вызывает `publish` с сериализованным CloudEvent JSON. Учесть, что `exchange.publish` асинхронен.  
- **Приёмка:** Тест проходит, мок фиксирует вызов `exchange.publish` с нужными данными, при этом ошибки логируются.  
- **Файлы:** добавить `tests/unit/test_publish_pipeline.py`.  
- **Проверка:** Запустить `pytest`: тесты должны успешно мокать RabbitMQ и проверять формат сообщения.  
- **Промпт (рус.):**  
  ```
  Напиши unit-тест для PublishPipeline: замокай соединение aio-pika (например, с pytest-mock или asynctest), и проверь, что при вызове process_item формируется сообщение с правильным JSON из CloudEvent. Учитывай, что функция асинхронна. 
  ```

**Итерация 10.2:** **Интеграционный тест с RabbitMQ.**  
- **Цель:** Организовать тест: поднять реальный RabbitMQ (через Docker), запустить Spider на небольшом примере, убедиться, что сообщения публикуются (например, засчитав количество сообщений в очереди с помощью pika или консоли).  
- **Приёмка:** Запуск `scrapy crawl mediapark` приводит к появлению событий (CloudEvent) в указанном exchange/очереди RabbitMQ.  
- **Файлы:** добавить `tests/integration/test_rabbit_publish.py`.  
- **Проверка:** Запустить тест: RabbitMQ-сервер поднят локально, скраппер публикует несколько сообщений (один тестовый item), получаемое из очереди JSON соответствует ожидаемому формату.  
- **Промпт (рус.):**  
  ```
  Настрой интеграционный тест: с помощью docker-compose запустить RabbitMQ и выполнить один Crawl, потом подключиться к RabbitMQ (pika) и прочитать сообщение из обменника. Проверить, что это валидный JSON CloudEvent. 
  ```

## Итоговый чеклист

- [ ] Удалены все упоминания локальной БД/Supabase/Celery【13†L185-L194】【13†L139-L142】.  
- [ ] Добавлен PublishPipeline, замена отправки в RabbitMQ【8†L19-L22】.  
- [ ] Зависимости очищены: нет `celery`, `redis`, `supabase-py`.  
- [ ] `PROJECT.md` и `BUILD_PLAN.md` обновлены под stateless-флоу.  
- [ ] `docker-compose.yml` и `.env.example` содержат только RabbitMQ и скрапер.  
- [ ] Юнит-тест PublishPipeline проходит; интеграционный тест подтверждает публикацию.

## Зависимости и DevOps

- **Python-зависимости (пример для pyproject.toml):** `scrapy`, `scrapy-playwright`, `aio-pika`, `pydantic` (v2), `orjson`, `tenacity` (для retry при публикации), `sentry-sdk`. Удалить: `supabase-py`, `psycopg2-binary`, `celery`, `redis`, `httpx`, `torch`/`PIL`/`rembg`, `flashtext`, `anthropic`, `open_clip`.  
- **Docker Compose:** см. выше.

