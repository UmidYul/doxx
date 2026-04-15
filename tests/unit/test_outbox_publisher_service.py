from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import orjson
import pytest

from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.observability import message_codes as obs_mc
from infrastructure.persistence.sqlite_store import SQLiteScraperStore
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import SQLiteOutboxReader
from services.publisher.publication_worker import PublicationWorker


class _StubRabbitPublisher:
    def __init__(
        self,
        *,
        fail_event_ids: set[str] | None = None,
        exception_factory=None,
        connect_failures: list[Exception] | None = None,
    ) -> None:
        self.fail_event_ids = set(fail_event_ids or set())
        self.exception_factory = exception_factory
        self.connect_failures = list(connect_failures or [])
        self.connect_calls = 0
        self.published = []

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_failures:
            raise self.connect_failures.pop(0)
        return None

    async def publish(self, event) -> None:
        if event.event_id in self.fail_event_ids:
            if self.exception_factory is not None:
                raise self.exception_factory()
            raise OSError("broker unavailable")
        self.published.append(event)

    async def close(self) -> None:
        return None


def _config(tmp_path: Path, *, publisher_name: str = "publisher-test") -> PublisherServiceConfig:
    return PublisherServiceConfig(
        rabbitmq_url="amqp://moscraper_publisher:test-pass@localhost:5672/moscraper",
        exchange_name="moscraper.events",
        exchange_type="topic",
        queue_name="scraper.products.v1",
        routing_key="listing.scraped.v1",
        publish_mandatory=True,
        declare_topology=False,
        heartbeat_seconds=30,
        connection_name=publisher_name,
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
    assert event.publication.outbox_status == "published"
    assert event.publication.attempt_number == 1
    assert event.publication.exchange_name == "moscraper.events"
    assert event.publication.queue_name == "scraper.products.v1"
    assert event.publication.routing_key == "listing.scraped.v1"
    assert event.publication.published_at is not None
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    payload = orjson.loads(str(outbox_row["payload_json"]))
    assert payload["publication"]["publisher_service"] == "publisher-test"
    assert payload["publication"]["outbox_status"] == "published"
    assert payload["publication"]["published_at"] is not None
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
async def test_failed_publish_uses_service_retry_policy(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    config = config.model_copy(update={"max_retries": 1, "retry_base_seconds": 1})
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(fail_event_ids={event_id}),
    )

    result = await worker.run_once()

    assert result.failed == 1
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "failed"
    assert outbox_row["retry_count"] == 1


@pytest.mark.asyncio
async def test_type_error_marks_outbox_row_terminal_failed(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(
            fail_event_ids={event_id},
            exception_factory=lambda: TypeError("bad payload shape"),
        ),
    )

    result = await worker.run_once()

    assert result.failed == 1
    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "failed"
    assert outbox_row["retry_count"] == 1
    assert "bad payload shape" in str(outbox_row["last_error"])


@pytest.mark.asyncio
async def test_run_once_logs_batch_completion(tmp_path: Path) -> None:
    store, config, _event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(),
    )

    with patch("services.publisher.publication_worker.log_publisher_event") as log_event:
        result = await worker.run_once()

    assert result.claimed == 1
    batch_calls = [call for call in log_event.call_args_list if call.args and call.args[0] == obs_mc.PUBLISHER_BATCH_COMPLETED]
    assert len(batch_calls) == 1
    assert batch_calls[0].kwargs["published"] == 1
    assert batch_calls[0].kwargs["failed"] == 0


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


@pytest.mark.asyncio
async def test_connect_failure_leaves_outbox_row_pending(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=_StubRabbitPublisher(connect_failures=[OSError("broker unavailable")]),
    )

    with pytest.raises(OSError, match="broker unavailable"):
        await worker.run_once()

    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "pending"
    assert outbox_row["retry_count"] == 0

    product_row = store.get_snapshot_row(scrape_run_id="mediapark:test-run", identity_key="mediapark:123")
    assert product_row is not None
    assert product_row["publication_state"] == "pending"

    attempts = store.get_publication_attempts(int(outbox_row["id"]))
    assert attempts == []


@pytest.mark.asyncio
async def test_run_forever_recovers_after_connect_error(tmp_path: Path) -> None:
    store, config, event_id = _seed_store(tmp_path)
    publisher = _StubRabbitPublisher(connect_failures=[OSError("broker unavailable")])
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=store, config=config),
        rabbit_publisher=publisher,
    )

    sleep_calls: list[float] = []

    async def _stop_after_second_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        if len(sleep_calls) >= 2:
            raise StopAsyncIteration

    with patch("services.publisher.publication_worker.log_publisher_event") as log_event:
        with (
            patch("services.publisher.publication_worker.asyncio.sleep", new=_stop_after_second_sleep),
            pytest.raises(StopAsyncIteration),
        ):
            await worker.run_forever()

    outbox_row = store.get_outbox_row(event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "published"
    assert publisher.connect_calls >= 2
    assert len(publisher.published) == 1
    run_failed_calls = [call for call in log_event.call_args_list if call.args and call.args[0] == obs_mc.PUBLISHER_RUN_FAILED]
    batch_calls = [call for call in log_event.call_args_list if call.args and call.args[0] == obs_mc.PUBLISHER_BATCH_COMPLETED]
    assert len(run_failed_calls) == 1
    assert len(batch_calls) == 1
