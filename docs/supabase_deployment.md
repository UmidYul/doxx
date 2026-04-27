# Supabase Deployment

## Runtime shape

Production contour:

`scraper-job -> scraper.publication_outbox -> publisher -> RabbitMQ -> CRM`

- `publisher` is the only always-on app service.
- `scraper-job` is invoked by host cron with `docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl <store>`.
- `scripts/bootstrap_scraper_db.py` applies the Postgres schema/bootstrap SQL using `SCRAPER_DB_MIGRATION_DSN`.

## Required env

- `SCRAPER_DB_BACKEND=postgres`
- `SCRAPER_DB_DSN`
- `SCRAPER_DB_MIGRATION_DSN`
- `RABBITMQ_URL`
- `RABBITMQ_MANAGEMENT_URL`
- `RABBITMQ_BOOTSTRAP_MANAGE_VHOST=false`
- `RABBITMQ_BOOTSTRAP_MANAGE_USERS=false`
- `RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS=false`

## Bootstrap

Run once per environment:

```powershell
python -m scripts.bootstrap_scraper_db
python -m scripts.bootstrap_rabbitmq
```

Or with containers:

```powershell
docker compose -f docker-compose.cloud.yml run --rm scraper-db-bootstrap
docker compose -f docker-compose.cloud.yml run --rm rabbitmq-bootstrap
```

## Cron template

Suggested staggered jobs on the VPS:

```cron
0 0 * * * cd /srv/moscraper && docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl mediapark
20 0 * * * cd /srv/moscraper && docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl texnomart
40 0 * * * cd /srv/moscraper && docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl uzum
0 1 * * * cd /srv/moscraper && docker compose -f docker-compose.cloud.yml run --rm scraper-job scrapy crawl alifshop
```

## Replay

Manual resend keeps history in `scraper.publication_attempts` and resets matching outbox rows to `pending`:

```powershell
python -m scripts.replay_outbox --store mediapark --status published --limit 50
python -m scripts.replay_outbox --event-id <event-id>
python -m scripts.replay_outbox --scrape-run-id <run-id> --status failed
```
