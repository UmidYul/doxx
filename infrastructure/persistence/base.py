from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.publication_event import ScraperProductEvent
from domain.scraped_product import ScrapedProductSnapshot


@dataclass(slots=True)
class ClaimedOutboxMessage:
    event_id: str
    exchange_name: str
    routing_key: str
    attempt_count: int
    payload: ScraperProductEvent


@dataclass(slots=True)
class PersistedRawProduct:
    raw_product_id: int
    outbox_id: int
    event_id: str
    payload_hash: str
    publication_state: str


class ScraperStore(Protocol):
    def register_scrape_run(
        self,
        *,
        scrape_run_id: str,
        store_name: str,
        spider_name: str,
        category_urls: list[str],
    ) -> None: ...

    def finish_scrape_run(
        self,
        *,
        scrape_run_id: str,
        status: str,
        stats: dict[str, object],
    ) -> None: ...

    def persist_snapshot(
        self,
        snapshot: ScrapedProductSnapshot,
        *,
        event_type: str,
        exchange_name: str,
        routing_key: str,
    ) -> PersistedRawProduct: ...

    def save_snapshot_and_enqueue(
        self,
        snapshot: ScrapedProductSnapshot,
        *,
        event_type: str,
        exchange_name: str,
        routing_key: str,
    ) -> str: ...

    def has_claimable_outbox_rows(self) -> bool: ...

    def claim_outbox_batch(
        self,
        *,
        batch_size: int,
        publisher_id: str,
        lease_seconds: int,
    ) -> list[ClaimedOutboxMessage]: ...

    def mark_outbox_published(
        self,
        *,
        event_id: str,
        publisher_id: str,
        exchange_name: str,
        routing_key: str,
        published_event: ScraperProductEvent | None = None,
    ) -> None: ...

    def mark_outbox_failed(
        self,
        *,
        event_id: str,
        publisher_id: str,
        exchange_name: str,
        routing_key: str,
        error_message: str,
        retryable: bool,
        max_retries: int | None = None,
        retry_base_seconds: int | None = None,
    ) -> None: ...

    def get_scrape_run_row(self, run_id: str) -> dict[str, object] | None: ...

    def get_snapshot_row(self, *, scrape_run_id: str, identity_key: str) -> dict[str, object] | None: ...

    def get_raw_product_images(self, raw_product_id: int) -> list[dict[str, object]]: ...

    def get_raw_product_specs(self, raw_product_id: int) -> list[dict[str, object]]: ...

    def get_outbox_row(self, event_id: str) -> dict[str, object] | None: ...

    def get_publication_attempts(self, outbox_id: int) -> list[dict[str, object]]: ...

    def close(self) -> None: ...
