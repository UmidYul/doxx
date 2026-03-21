# Moscraper

Stateless Scrapy service: scrape listings → minimal normalization → **RabbitMQ** (CloudEvents JSON).

- **Architecture & contract:** [PROJECT.md](PROJECT.md)  
- **Implementation checklist:** [BUILD_PLAN.md](BUILD_PLAN.md)  
- **Env template:** [.env.example](.env.example)  
- **Local broker:** `docker compose up -d`  

| Date | Change |
|------|--------|
| 2026-03-21 | Migrated to RabbitMQ-only publisher; removed DB/CRM REST/delta/image pipeline; optional `playwright` extra. |

## Quick start

```bash
python -m pip install -e .
cp .env.example .env
docker compose up -d rabbitmq
# optional: set MOSCRAPER_DISABLE_PUBLISH=true for crawl without broker
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5
```

Optional browser-backed spiders: `python -m pip install -e ".[playwright]"` then `playwright install`.
