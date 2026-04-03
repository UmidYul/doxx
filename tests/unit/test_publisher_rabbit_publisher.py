from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aio_pika import DeliveryMode

from domain.publication_event import PublicationMetadata, ScrapedProductPayload, ScraperProductEvent
from services.publisher.config import PublisherServiceConfig
from services.publisher.rabbit_publisher import RabbitMQPublisher


def _config() -> PublisherServiceConfig:
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
            outbox_status="publishing",
            attempt_number=1,
            publisher_service="publisher-test",
            outbox_created_at="2026-04-03T12:00:15Z",
        ),
    )


@pytest.mark.asyncio
async def test_rabbit_publisher_declares_durable_topology_and_persistent_message() -> None:
    config = _config()
    publisher = RabbitMQPublisher(config=config)
    connection = AsyncMock()
    channel = AsyncMock()
    exchange = AsyncMock()
    queue = AsyncMock()
    connection.channel.return_value = channel
    channel.declare_exchange.return_value = exchange
    channel.declare_queue.return_value = queue

    async def _connect(url: str):
        assert url == config.rabbitmq_url
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
