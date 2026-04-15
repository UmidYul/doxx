from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aio_pika import DeliveryMode
from aio_pika.exceptions import ChannelInvalidStateError

from domain.publication_event import PublicationMetadata, ScrapedProductPayload, ScraperProductEvent
from infrastructure.observability import message_codes as obs_mc
from services.publisher.config import PublisherServiceConfig
from services.publisher.rabbit_publisher import RabbitMQPublisher


def _config(*, declare_topology: bool) -> PublisherServiceConfig:
    return PublisherServiceConfig(
        rabbitmq_url="amqp://moscraper_publisher:test-pass@localhost:5672/moscraper",
        exchange_name="moscraper.events",
        exchange_type="topic",
        queue_name="scraper.products.v1",
        routing_key="listing.scraped.v1",
        publish_mandatory=True,
        declare_topology=declare_topology,
        heartbeat_seconds=30,
        connection_name="publisher-test",
        batch_size=50,
        lease_seconds=60,
        max_retries=8,
        retry_base_seconds=15,
        poll_interval_seconds=0.1,
        publisher_service_name="publisher-test",
        scraper_db_path="data/scraper/scraper.db",
    )


def _event() -> ScraperProductEvent:
    return ScraperProductEvent(
        event_id="evt-1",
        event_type="scraper.product.scraped.v1",
        schema_version=1,
        store_name="mediapark",
        source_id="123",
        source_url="https://mediapark.uz/products/view/demo-phone-123",
        scrape_run_id="run-1",
        scraped_at="2026-04-03T12:00:15Z",
        payload_hash="sha256:abc",
        structured_payload=ScrapedProductPayload(
            store_name="mediapark",
            source_url="https://mediapark.uz/products/view/demo-phone-123",
            source_id="123",
            title="Demo Phone",
            brand="DemoBrand",
            price_raw="1000000",
            in_stock=True,
            raw_specs={"Color": "Black"},
            image_urls=["https://mediapark.uz/img/demo.jpg"],
            description="Demo",
            category_hint="phone",
            external_ids={"mediapark": "123"},
            scraped_at="2026-04-03T12:00:15Z",
            payload_hash="sha256:abc",
            raw_payload_snapshot={"title": "Demo Phone"},
            scrape_run_id="run-1",
            identity_key="mediapark:123",
        ),
        publication=PublicationMetadata(
            publication_version=1,
            exchange_name="moscraper.events",
            queue_name="scraper.products.v1",
            routing_key="listing.scraped.v1",
            outbox_status="published",
            attempt_number=1,
            publisher_service="publisher-test",
            outbox_created_at="2026-04-03T12:00:15Z",
            published_at="2026-04-03T12:00:16Z",
        ),
    )


@pytest.mark.asyncio
async def test_rabbit_publisher_declares_durable_topology_and_persistent_message() -> None:
    config = _config(declare_topology=True)
    publisher = RabbitMQPublisher(config=config)
    connection = AsyncMock()
    channel = AsyncMock()
    exchange = AsyncMock()
    queue = AsyncMock()
    connection.channel.return_value = channel
    channel.declare_exchange.return_value = exchange
    channel.declare_queue.return_value = queue

    async def _connect(url: str, **kwargs):
        assert url == config.rabbitmq_url
        assert kwargs["heartbeat"] == 30
        assert kwargs["client_properties"]["connection_name"] == "publisher-test"
        return connection

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        await publisher.connect()
        await publisher.publish(_event())
    finally:
        module.aio_pika.connect_robust = original

    channel.declare_exchange.assert_awaited_once()
    _, exchange_kwargs = channel.declare_exchange.call_args
    assert exchange_kwargs["durable"] is True

    channel.declare_queue.assert_awaited_once()
    _, queue_kwargs = channel.declare_queue.call_args
    assert queue_kwargs["durable"] is True
    queue.bind.assert_awaited_once()

    exchange.publish.assert_awaited_once()
    message = exchange.publish.call_args.args[0]
    assert message.delivery_mode == DeliveryMode.PERSISTENT
    assert message.type == "scraper.product.scraped.v1"
    assert message.headers["schema_version"] == 1


@pytest.mark.asyncio
async def test_rabbit_publisher_skips_topology_declare_when_disabled() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)
    connection = AsyncMock()
    channel = AsyncMock()
    exchange = AsyncMock()
    connection.channel.return_value = channel
    channel.get_exchange.return_value = exchange

    async def _connect(url: str, **kwargs):
        assert url == config.rabbitmq_url
        assert kwargs["heartbeat"] == 30
        assert kwargs["client_properties"]["connection_name"] == "publisher-test"
        return connection

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        await publisher.connect()
        await publisher.publish(_event())
    finally:
        module.aio_pika.connect_robust = original

    channel.get_exchange.assert_awaited_once_with("moscraper.events", ensure=False)
    channel.declare_exchange.assert_not_called()
    channel.declare_queue.assert_not_called()
    exchange.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_rabbit_publisher_reconnects_when_cached_connection_is_closed() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)

    stale_connection = SimpleNamespace(is_closed=True)
    publisher._connection = stale_connection  # type: ignore[attr-defined]

    connection = AsyncMock()
    connection.is_closed = False
    channel = AsyncMock()
    channel.is_closed = False
    exchange = AsyncMock()
    connection.channel.return_value = channel
    channel.get_exchange.return_value = exchange

    async def _connect(url: str, **kwargs):
        assert url == config.rabbitmq_url
        assert kwargs["client_properties"]["connection_name"] == "publisher-test"
        return connection

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        await publisher.connect()
    finally:
        module.aio_pika.connect_robust = original

    assert publisher._connection is connection  # type: ignore[attr-defined]
    assert publisher._channel is channel  # type: ignore[attr-defined]
    assert publisher._exchange is exchange  # type: ignore[attr-defined]
    channel.get_exchange.assert_awaited_once_with("moscraper.events", ensure=False)


@pytest.mark.asyncio
async def test_rabbit_publisher_retries_once_after_recoverable_publish_failure() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)

    connection1 = AsyncMock()
    connection1.is_closed = False
    channel1 = AsyncMock()
    channel1.is_closed = False
    exchange1 = AsyncMock()
    exchange1.publish.side_effect = ChannelInvalidStateError("channel closed")
    connection1.channel.return_value = channel1
    channel1.get_exchange.return_value = exchange1

    connection2 = AsyncMock()
    connection2.is_closed = False
    channel2 = AsyncMock()
    channel2.is_closed = False
    exchange2 = AsyncMock()
    connection2.channel.return_value = channel2
    channel2.get_exchange.return_value = exchange2

    connect_calls = 0

    async def _connect(url: str, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        assert url == config.rabbitmq_url
        return connection1 if connect_calls == 1 else connection2

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        await publisher.publish(_event())
    finally:
        module.aio_pika.connect_robust = original

    assert connect_calls == 2
    exchange1.publish.assert_awaited_once()
    exchange2.publish.assert_awaited_once()
    channel1.close.assert_awaited_once()
    connection1.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_rabbit_publisher_logs_connect_failure() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)

    async def _connect(url: str, **kwargs):
        assert url == config.rabbitmq_url
        raise OSError("broker unavailable")

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        with patch("services.publisher.rabbit_publisher.log_publisher_event") as log_event:
            with pytest.raises(OSError, match="broker unavailable"):
                await publisher.connect()
    finally:
        module.aio_pika.connect_robust = original

    log_event.assert_called_once()
    assert log_event.call_args.args[0] == obs_mc.PUBLISHER_CONNECT_FAILED
    assert log_event.call_args.kwargs["severity"] == "error"


@pytest.mark.asyncio
async def test_rabbit_publisher_logs_retry_on_recoverable_publish_failure() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)

    connection1 = AsyncMock()
    connection1.is_closed = False
    channel1 = AsyncMock()
    channel1.is_closed = False
    exchange1 = AsyncMock()
    exchange1.publish.side_effect = ChannelInvalidStateError("channel closed")
    connection1.channel.return_value = channel1
    channel1.get_exchange.return_value = exchange1

    connection2 = AsyncMock()
    connection2.is_closed = False
    channel2 = AsyncMock()
    channel2.is_closed = False
    exchange2 = AsyncMock()
    connection2.channel.return_value = channel2
    channel2.get_exchange.return_value = exchange2

    connect_calls = 0

    async def _connect(url: str, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        return connection1 if connect_calls == 1 else connection2

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        with patch("services.publisher.rabbit_publisher.log_publisher_event") as log_event:
            await publisher.publish(_event())
    finally:
        module.aio_pika.connect_robust = original

    assert connect_calls == 2
    retry_calls = [call for call in log_event.call_args_list if call.args and call.args[0] == obs_mc.PUBLISHER_PUBLISH_RETRY]
    assert len(retry_calls) == 1


@pytest.mark.asyncio
async def test_rabbit_publisher_rejects_contract_drift_before_publish() -> None:
    config = _config(declare_topology=False)
    publisher = RabbitMQPublisher(config=config)
    connection = AsyncMock()
    connection.is_closed = False
    channel = AsyncMock()
    channel.is_closed = False
    exchange = AsyncMock()
    connection.channel.return_value = channel
    channel.get_exchange.return_value = exchange

    async def _connect(url: str, **kwargs):
        assert url == config.rabbitmq_url
        return connection

    import services.publisher.rabbit_publisher as module

    original = module.aio_pika.connect_robust
    module.aio_pika.connect_robust = _connect
    try:
        broken = _event().model_copy(
            update={
                "publication": _event().publication.model_copy(
                    update={"publisher_service": None}
                )
            }
        )
        with pytest.raises(ValueError, match="publication.publisher_service"):
            await publisher.publish(broken)
    finally:
        module.aio_pika.connect_robust = original

    exchange.publish.assert_not_called()
