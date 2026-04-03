from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.persistence.sqlite_store import PersistedRawProduct, SQLiteScraperStore


@dataclass(slots=True)
class PersistedScrapyItem:
    scrape_run_id: str
    raw_product_id: int
    outbox_id: int
    event_id: str
    payload_hash: str
    publication_state: str


class ScraperPersistenceService:
    def __init__(self, *, store: SQLiteScraperStore | None = None) -> None:
        self._store = store or SQLiteScraperStore.from_settings()

    @property
    def store(self) -> SQLiteScraperStore:
        return self._store

    def start_run(
        self,
        *,
        scrape_run_id: str,
        store_name: str,
        spider_name: str,
        category_urls: list[str],
    ) -> None:
        self._store.register_scrape_run(
            scrape_run_id=scrape_run_id,
            store_name=store_name,
            spider_name=spider_name,
            category_urls=category_urls,
        )

    def finish_run(
        self,
        *,
        scrape_run_id: str,
        status: str,
        stats: dict[str, object],
    ) -> None:
        self._store.finish_scrape_run(
            scrape_run_id=scrape_run_id,
            status=status,
            stats=stats,
        )

    def persist_item(
        self,
        item: dict[str, Any],
        *,
        scrape_run_id: str,
        event_type: str,
        exchange_name: str,
        routing_key: str,
    ) -> PersistedScrapyItem:
        snapshot = ScrapedProductSnapshot.from_scrapy_item(item, scrape_run_id=scrape_run_id)
        persisted = self._store.persist_snapshot(
            snapshot,
            event_type=event_type,
            exchange_name=exchange_name,
            routing_key=routing_key,
        )
        return self._to_result(scrape_run_id=scrape_run_id, persisted=persisted)

    def close(self) -> None:
        self._store.close()

    def _to_result(self, *, scrape_run_id: str, persisted: PersistedRawProduct) -> PersistedScrapyItem:
        return PersistedScrapyItem(
            scrape_run_id=scrape_run_id,
            raw_product_id=persisted.raw_product_id,
            outbox_id=persisted.outbox_id,
            event_id=persisted.event_id,
            payload_hash=persisted.payload_hash,
            publication_state=persisted.publication_state,
        )
