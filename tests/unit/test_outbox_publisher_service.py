from __future__ import annotations

from pathlib import Path

import pytest

from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.persistence.sqlite_store import SQLiteScraperStore
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import SQLiteOutboxReader
from services.publisher.publication_worker import PublicationWorker


class _StubRabbitPublisher:
    def __init__(self, *, fail_event_ids: set[str] | None = None) -> None:
        self.fail_event_ids = set(fail_event_ids or set())
        self.published = []

    async def connect(self) -> None:
        return None

    async def publish(self, event) -> None:
        if event.event_id in self.fail_event_ids:
            raise OSError("broker unavailable")
        self.published.append(event)

    async def close(self) -> None:
        return None


def _config(tmp_path: Path, *, publisher_name: str = "publisher-test") -> PublisherServiceConfig:
    return PublisherServiceConfig(
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        exchange_name="moscraper.events",
        exchange_type="topic",
        queue_name="scraper.products.v1",
        routing_key="listing.scraped.v1",
        publish_mandatory=True,
        batch_size=50,
        lease_seconds=60,
        max_retries=8,
        retry_base_seconds=15,
        poll_interval_seconds=0.1,
        publisher_service_name=publisher_name,
        scraper_db_path=str(tmp_path / "scraper.db"),
    )


def _seed_store(tmp_path: Path, *, source_id: str = "123") -> tuple[SQLiteScraperStore, PublisherServiceConfig, str]:
    config = _config(tmp_path)
    store = SQLiteScraperStore(config.scraper_db_path)
    run_id = "mediapark:test-run"
    store.register_scrape_run(
        scrape_run_id=run_id,
        store_name="mediapark",
        spider_name="mediapark",
        category_urls=[],
    )
    snapshot = ScrapedProductSnapshot.from_scrapy_item(
        {
            "source": "mediapark",
            "url": f"https://mediapark.uz/products/view/demo-phone-{source_id}",
            "source_id": source_id,
            "title": f"Demo Phone {source_id}",
            "price_str": "1000000",
            "in_stock": True,
            "raw_specs": {"Color": "Black"},
            "image_urls": [f"https://mediapark.uz/img/demo-{source_id}.jpg"],
        },
        scrape_run_id=run_id,
    )
    event_id = store.save_snapshot_and_enqueue(
        snapshot,
        event_type="scraper.product.scraped.v1",
        exchange_name=config.exchange_name,
        routing_key=config.routing_key,
    )
    return store, config, event_id


@pytest.mark.asyncio
async def test_pending_outbox_row_published(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(),
    )

    result = await worker.run_once()

    assert result.claimed == 1
    assert result.published == 1
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "published"


@pytest.mark.asyncio
async def test_success_marks_row_published_and_logs_attempt(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    publisher = _StubRabbitPublisher()
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=publisher,
    )

    await worker.run_once()

    assert len(publisher.published) == 1
    event = publisher.published[0]
    assert event.schema_version == 1
    assert event.publication.publisher_service == "publisher-test"
    assert event.publication.attempt_number == 1
    assert event.publication.exchange_name == "moscraper.events"
    assert event.publication.queue_name == "scraper.products.v1"
    assert event.publication.routing_key == "listing.scraped.v1"
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    attempts = store.get_publication_attempts(int(outbox_row["id"]))
    assert len(attempts) == 1
    assert attempts[0]["success"] == 1
    assert attempts[0]["publisher_name"] == "publisher-test"


@pytest.mark.asyncio
async def test_failed_publish_increments_retry_and_last_error(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(fail_event_ids={event_id}),
    )

    result = await worker.run_once()

    assert result.published == 0
    assert result.failed == 1
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "retryable"
    assert outbox_row["retry_count"] == 1
    assert "broker unavailable" in str(outbox_row["last_error"])


@pytest.mark.asyncio
async def test_failed_publish_logs_attempt(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(fail_event_ids={event_id}),
    )

    await worker.run_once()

    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    attempts = store.get_publication_attempts(int(outbox_row["id"]))
    assert len(attempts) == 1
    assert attempts[0]["success"] == 0
    assert attempts[0]["error_message"] == "broker unavailable"


@pytest.mark.asyncio
async def test_publisher_survives_one_bad_row_and_continues(tmp_path: Path) -> None:
    store, config, first_event_id = _seed_store(tmp_path, source_id="123")
    _store2, _config2, second_event_id = _seed_store(tmp_path, source_id="456")
    publisher = _StubRabbitPublisher(fail_event_ids={first_event_id})
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=publisher,
    )

    result = await worker.run_once()

    assert result.claimed == 2
    assert result.published == 1
    assert result.failed == 1
    first_row = store.get_outbox_row(first_event_id)
    second_row = store.get_outbox_row(second_event_id)
    assert first_row is not None and first_row["status"] == "retryable"
    assert second_row is not None and second_row["status"] == "published"
