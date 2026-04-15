# Перенос RabbitMQ в CloudAMQP Dedicated без смены контракта

## Summary
- По состоянию на 12 апреля 2026, `Supabase` не подходит как “хостинг текущего RabbitMQ”: `Supabase Queues` это отдельная очередь-система, а не managed `RabbitMQ/AMQP` broker, поэтому такой путь означал бы уже смену транспорта, а не перенос текущего runtime. Источники: [Supabase Queues](https://supabase.com/docs/guides/queues), [CloudAMQP plans](https://www.cloudamqp.com/plans.html), [CloudAMQP HTTP API](https://www.cloudamqp.com/docs/http.html).
- Целевая схема: `local scraper -> CloudAMQP -> local CRM`. На этой итерации в облако переносится только broker; `scraper` и CRM остаются на ноутбуках.
- Контракт и topology names не меняются: `moscraper.events`, `scraper.products.v1`, `crm.products.import.v1`, retry-lanes и DLQ остаются прежними. CRM по-прежнему читает только `crm.products.import.v1`.

## Important Interface Changes
- Зафиксировать cloud-mode env surface:
  - `RABBITMQ_URL` = полный `amqps://...` URL для publisher/scraper runtime.
  - `RABBITMQ_CRM_URL` = полный `amqps://...` URL с CRM credentials для smoke и repo-side consumer checks.
  - `RABBITMQ_MANAGEMENT_URL` = `https://...` management endpoint CloudAMQP.
  - `RABBITMQ_VHOST=moscraper`.
  - `RABBITMQ_DECLARE_TOPOLOGY=false` во всех runtime-процессах.
  - `RABBITMQ_BOOTSTRAP_CREATE_ADMIN_USER=false` в cloud mode.
- Полевая форма сообщения не меняется: в Rabbit продолжает уходить тот же `ScraperProductEvent`; `publication`, `structured_payload`, `payload_hash`, `raw_specs` и прочие поля остаются без транспортного редизайна.
- Для hosted broker использовать provider-supplied URLs verbatim; не собирать URL вручную из `host:port`, потому что у managed Rabbit часто специфичны vhost name, TLS-параметры и URL-encoding.

## Implementation Changes
- Провизионить один `CloudAMQP Dedicated` instance в ближайшем доступном central-EU регионе; default choice для плана: Frankfurt-equivalent/central EU, если доступен у провайдера.
- Сохранить один vhost `moscraper` и существующую topology source of truth; one-shot bootstrap выполняется через [scripts/bootstrap_rabbitmq.py](c:\Users\Lenovo\Desktop\doxx\scripts\bootstrap_rabbitmq.py) по management API over HTTPS.
- Разделить control-plane и app-runtime credentials:
  - provider master/admin credential использовать только для bootstrap/UI;
  - runtime users оставить отдельными: `moscraper_publisher` и `moscraper_crm`;
  - текущие локальные пароли не переиспользовать в публичном broker, а заменить новыми длинными cloud-only секретами.
- Изменить bootstrap-логику для managed режима:
  - cloud mode не должен пытаться создавать второй admin account;
  - bootstrap должен создавать только app-users, permissions, exchanges, queues и bindings;
  - least-privilege модель оставить текущей: publisher пишет только в `moscraper.events`, CRM читает `crm.products.import.v1` и `.dlq`, и пишет только в `crm.products.retry`.
- Развести local и cloud execution path:
  - [docker-compose.yml](c:\Users\Lenovo\Desktop\doxx\docker-compose.yml) оставить как fully-local dev stack;
  - добавить отдельный cloud compose path или compose profile, где нет локального `rabbitmq` service и нет `depends_on` на local broker;
  - в cloud path допускается только one-shot bootstrap container плюс `scraper` и `publisher`, работающие против внешнего `amqps://` broker.
- Адаптировать smoke/tooling под внешний broker:
  - [scripts/rabbit_smoke.py](c:\Users\Lenovo\Desktop\doxx\scripts\rabbit_smoke.py) перестать хардкодить `localhost:5672` для CRM-side connection;
  - smoke должен работать через `RABBITMQ_CRM_URL`;
  - сохранить два режима: `bootstrap + smoke` для первого запуска и `--skip-bootstrap` для регулярной проверки уже поднятого cloud broker.
- Сохранить runtime hardening:
  - `RABBITMQ_DECLARE_TOPOLOGY=false` для publisher/scraper;
  - connection names и heartbeats оставить явными, чтобы в CloudAMQP UI были видны отдельные подключения `publisher-service`, `scraper-runtime`, `crm-consumer`;
  - transport только по `amqps://` и `https://`.
- Обновить docs и env примеры:
  - явно разделить `local broker mode` и `cloud broker mode`;
  - в cloud docs указать, что local Rabbit остаётся только для dev/rollback, а production-like path уходит в managed broker;
  - CRM handoff перевести с LAN IP на CloudAMQP URLs.

## Rollout and Acceptance
- Сначала провизионить CloudAMQP instance и сохранить 3 набора секретов: management admin, publisher runtime, CRM runtime.
- Затем выполнить bootstrap topology против CloudAMQP и подтвердить наличие `moscraper.events`, `scraper.products.v1`, `crm.products.import.v1`, retry queues и `crm.products.import.v1.dlq`.
- После этого сначала перевести CRM consumer на cloud broker и проверить стабильный `consumer_ready` на `crm.products.import.v1`.
- Затем перевести scraper/publisher на cloud broker, отправить synthetic smoke batch, а потом реальную пачку из 10–15 телефонов из scraper DB.
- Считать cutover успешным только если одновременно выполняются все критерии:
  - сообщения приходят в `crm.products.import.v1`;
  - CRM помечает их как `processed` или `duplicate`, а не `quarantined`;
  - retry-path возвращает сообщения из `30s` обратно в main queue;
  - terminal failures попадают в `crm.products.import.v1.dlq`;
  - publisher и consumer переживают краткий интернет-сбой без ручного ремонта topology.
- Rollback оставить максимально дешёвым: local Rabbit stack не удалять, а держать как fallback; rollback = возврат env на local broker и рестарт процессов.

## Test Plan
- Unit tests:
  - cloud bootstrap mode не создаёт второй admin-user, но идемпотентно создаёт vhost, app-users, permissions, exchanges, queues и bindings;
  - smoke script работает с внешним `RABBITMQ_CRM_URL`;
  - publisher корректно публикует через `amqps://` при `RABBITMQ_DECLARE_TOPOLOGY=false`.
- Integration tests:
  - bootstrap against CloudAMQP;
  - main-path smoke publish/read;
  - retry path `30s -> main`;
  - reject path `main -> dlq`.
- End-to-end acceptance:
  - отправить 10–15 phone products из реальной scraper DB;
  - проверить в CRM логах/таблицах, что batch дошёл как `processed`/`duplicate`;
  - убедиться, что нет накопления stuck messages в `crm.products.import.v1` и long-lived quarantined из-за transport mismatch.

## Assumptions and Defaults
- Оба приложения пока остаются локальными; меняем только местоположение broker.
- Выбран `CloudAMQP Dedicated`, а не shared tier.
- Default region choice: ближайший central-EU вариант, если доступен.
- `Supabase` остаётся только storage/backend CRM; transport в `Supabase Queues` в этой итерации не переносится.
- Бизнес-контракт между scraper и CRM остаётся текущим RabbitMQ-контрактом без смены event schema.
