from __future__ import annotations

import logging

from application.ingestion.persistence_service import ScraperPersistenceService
from config.settings import settings
from infrastructure.observability.correlation import build_run_id
from infrastructure.persistence.base import ScraperStore
from infrastructure.persistence.factory import build_scraper_store

logger = logging.getLogger(__name__)


class ScraperStoragePipeline:
    def __init__(self) -> None:
        self._store: ScraperStore | None = None
        self._service: ScraperPersistenceService | None = None
        self._scrape_run_id: str | None = None
        self._items_persisted: int = 0
        self._products_with_specs: int = 0
        self._products_without_specs: int = 0
        self._products_with_images: int = 0
        self._products_without_images: int = 0

    @classmethod
    def from_crawler(cls, _crawler):
        return cls()

    def open_spider(self, spider) -> None:
        self._store = build_scraper_store(
            backend=settings.resolved_scraper_db_backend(),
            sqlite_path=settings.SCRAPER_DB_PATH,
            postgres_dsn=settings.SCRAPER_DB_DSN,
        )
        self._service = ScraperPersistenceService(store=self._store)
        run_id = getattr(spider, "_scrape_run_id", None) or getattr(spider, "_parser_run_id", None) or build_run_id(spider.name)
        spider._scrape_run_id = run_id
        spider._parser_run_id = run_id
        self._scrape_run_id = run_id
        self._items_persisted = 0
        self._products_with_specs = 0
        self._products_without_specs = 0
        self._products_with_images = 0
        self._products_without_images = 0
        category_urls = list(spider.start_category_urls()) if hasattr(spider, "start_category_urls") else []
        self._service.start_run(
            scrape_run_id=run_id,
            store_name=getattr(spider, "store_name", spider.name),
            spider_name=spider.name,
            category_urls=[str(url) for url in category_urls],
        )

    def process_item(self, item, spider):
        if self._service is None or self._store is None or self._scrape_run_id is None:
            raise RuntimeError("ScraperStoragePipeline: store not initialized")

        persisted = self._service.persist_item(
            dict(item),
            scrape_run_id=self._scrape_run_id,
            event_type=settings.SCRAPER_OUTBOX_EVENT_TYPE,
            exchange_name=settings.RABBITMQ_EXCHANGE,
            routing_key=settings.RABBITMQ_ROUTING_KEY,
        )
        item["_scrape_run_id"] = persisted.scrape_run_id
        item["_payload_hash"] = persisted.payload_hash
        item["_outbox_event_id"] = persisted.event_id
        item["_raw_product_id"] = persisted.raw_product_id
        item["_publication_state"] = persisted.publication_state
        self._items_persisted += 1
        if item.get("raw_specs"):
            self._products_with_specs += 1
        else:
            self._products_without_specs += 1
        if item.get("image_urls"):
            self._products_with_images += 1
        else:
            self._products_without_images += 1
        logger.info(
            "scraper_db_saved store=%s source_id=%s url=%s event_id=%s raw_product_id=%s",
            item.get("source"),
            item.get("source_id") or item.get("external_id"),
            item.get("url"),
            persisted.event_id,
            persisted.raw_product_id,
        )
        return item

    def close_spider(self, spider) -> None:
        if self._service is None or self._store is None or self._scrape_run_id is None:
            return
        crawl_stats: dict[str, object] = {}
        crawler = getattr(spider, "crawler", None)
        stats_collector = getattr(crawler, "stats", None)
        if stats_collector is not None and hasattr(stats_collector, "get_stats"):
            crawl_stats.update(dict(stats_collector.get_stats()))
        crawl_registry = getattr(spider, "crawl_registry", None)
        if crawl_registry is not None and hasattr(crawl_registry, "snapshot_metrics"):
            crawl_stats.update(dict(crawl_registry.snapshot_metrics()))
        items_failed = int(
            crawl_stats.get("items_failed")
            or crawl_stats.get("product_parse_failed_total")
            or crawl_stats.get("item_dropped_count")
            or 0
        )
        items_scraped = int(
            crawl_stats.get("items_scraped")
            or crawl_stats.get("product_items_yielded_total")
            or crawl_stats.get("item_scraped_count")
            or self._items_persisted
        )
        if self._items_persisted > 0:
            crawl_stats["products_with_specs_total"] = self._products_with_specs
            crawl_stats["products_without_specs_total"] = self._products_without_specs
            crawl_stats["products_with_images_total"] = self._products_with_images
            crawl_stats["products_without_images_total"] = self._products_without_images
            crawl_stats["spec_coverage_ratio"] = self._products_with_specs / self._items_persisted
            crawl_stats["image_coverage_ratio"] = self._products_with_images / self._items_persisted
        crawl_stats["items_scraped"] = items_scraped
        crawl_stats["items_persisted"] = self._items_persisted
        crawl_stats["items_failed"] = items_failed
        finish_reason = str(crawl_stats.get("finish_reason") or "finished")
        status = "failed" if finish_reason != "finished" else ("partial_failure" if items_failed > 0 else "completed")
        self._service.finish_run(
            scrape_run_id=self._scrape_run_id,
            status=status,
            stats=crawl_stats,
        )
        logger.info(
            "scrape_run_summary run_id=%s store=%s status=%s scraped_items=%s persisted_items=%s failed_pdp=%s pages_visited=%s spec_coverage_ratio=%s image_coverage_ratio=%s",
            self._scrape_run_id,
            getattr(spider, "store_name", spider.name),
            status,
            items_scraped,
            self._items_persisted,
            items_failed,
            crawl_stats.get("pages_visited_total"),
            crawl_stats.get("spec_coverage_ratio"),
            crawl_stats.get("image_coverage_ratio"),
        )
        self._service.close()
        self._service = None
        self._store = None
