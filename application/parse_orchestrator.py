"""Single-process Scrapy entrypoint: one crawler run, no Celery or parse queue."""

from __future__ import annotations

from typing import Any

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


def run_spider(spider_name: str, *, settings_overrides: dict[str, Any] | None = None) -> None:
    """Run ``scrapy crawl <spider_name>`` in-process and block until the crawl finishes.

    Must be started with the project root (where ``scrapy.cfg`` lives) as the working directory.
    """
    settings = get_project_settings()
    if settings_overrides:
        settings.update(settings_overrides, priority="cmdline")
    process = CrawlerProcess(settings)
    process.crawl(spider_name)
    process.start()
