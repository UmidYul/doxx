# Moscraper Operator UI

Minimal local UI for starting and observing Scrapy runs.

## Run

```powershell
python -m services.ui_api.main --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## Scope

The UI is intentionally narrow:

- choose one store spider
- optionally limit the run to a category, brand, or exact category URL
- set a custom time limit in minutes
- set a custom item limit
- set a custom parse/request interval in seconds
- run until manually stopped
- stream logs while the subprocess is running
- stop a running subprocess
- show a short run summary
- show outbox publication status for the selected run
- publish pending UI outbox rows to RabbitMQ on demand
- show minimal diagnostics
- switch UI language between Russian (default) and Uzbek

It does not manage outbox replay, CRM cutover, exports, or RabbitMQ queues.

## Runtime Notes

Scrapy runs are launched as subprocesses. The UI forces local scraper persistence for its own runs:

```text
SCRAPER_DB_BACKEND=sqlite
SCRAPER_DB_PATH=data/scraper/ui_runs.db
TRANSPORT_TYPE=disabled
```

Run metadata is stored in:

```text
data/ui/runs.json
```

Run logs are stored in:

```text
data/ui/logs/
```

The optional parse interval is passed to Scrapy as:

```text
DOWNLOAD_DELAY=<seconds>
```

Leave it empty to use the project's normal Scrapy delay settings.

Targeting fields are passed as Scrapy spider arguments:

```text
-a category=phone
-a brand=Apple
-a category_url=https://example.uz/category/path
```

When a store has a known URL for the selected category/brand, the spider starts from that URL. Otherwise it starts from the closest category seed and filters parsed products by normalized `category_hint` and `brand` before persistence/outbox.

## Publication

Scraping writes products to the local UI scraper DB and creates pending outbox rows. CRM does not see those rows directly.

Use the `Publication` block in a run detail page to publish pending rows to RabbitMQ. After RabbitMQ publication, downstream CRM consumers can read the messages from their queue.
