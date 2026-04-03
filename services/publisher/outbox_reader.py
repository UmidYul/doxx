from __future__ import annotations

from infrastructure.persistence.sqlite_store import ClaimedOutboxMessage, SQLiteScraperStore

from services.publisher.config import PublisherServiceConfig


class SQLiteOutboxReader:
    def __init__(
        self,
        *,
        store: SQLiteScraperStore | None = None,
        config: PublisherServiceConfig | None = None,
    ) -> None:
        self._config = config or PublisherServiceConfig.from_settings()
        self._store = store or SQLiteScraperStore(self._config.scraper_db_path)

    @property
    def store(self) -> SQLiteScraperStore:
        return self._store

    def claim_batch(self) -> list[ClaimedOutboxMessage]:
        return self._store.claim_outbox_batch(
            batch_size=self._config.batch_size,
            publisher_id=self._config.publisher_service_name,
            lease_seconds=self._config.lease_seconds,
        )

    def mark_published(self, *, event_id: str) -> None:
        self._store.mark_outbox_published(
            event_id=event_id,
            publisher_id=self._config.publisher_service_name,
            exchange_name=self._config.exchange_name,
            routing_key=self._config.routing_key,
        )

    def mark_failed(self, *, event_id: str, error_message: str, retryable: bool) -> None:
        self._store.mark_outbox_failed(
            event_id=event_id,
            publisher_id=self._config.publisher_service_name,
            exchange_name=self._config.exchange_name,
            routing_key=self._config.routing_key,
            error_message=error_message,
            retryable=retryable,
        )

    def close(self) -> None:
        self._store.close()
