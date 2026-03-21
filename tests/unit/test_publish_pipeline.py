from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from config.settings import settings
from infrastructure.pipelines.publish_pipeline import PublishPipeline
from infrastructure.publishers.rabbitmq_publisher import RabbitMQPublisher


def _sample_item() -> dict:
    return {
        "url": "https://mediapark.uz/p/1",
        "_normalized": {
            "store": "mediapark",
            "url": "https://mediapark.uz/p/1",
            "title": "Phone",
            "source_id": "1",
            "price_raw": "10 сум",
            "price": 10.0,
            "currency": "UZS",
            "in_stock": True,
            "brand": None,
            "raw_specs": {},
            "description": None,
            "image_urls": [],
        },
    }


@pytest.fixture
def aio_pika_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Patch aio-pika at the publisher module so no real broker is used."""
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel = AsyncMock()
    channel.declare_exchange = AsyncMock(return_value=exchange)
    connection = AsyncMock()
    connection.channel = AsyncMock(return_value=channel)
    connect_robust = AsyncMock(return_value=connection)
    monkeypatch.setattr(
        "infrastructure.publishers.rabbitmq_publisher.aio_pika.connect_robust",
        connect_robust,
    )
    return SimpleNamespace(
        connect_robust=connect_robust,
        connection=connection,
        channel=channel,
        exchange=exchange,
    )


@pytest.mark.asyncio
async def test_publish_pipeline_triggers_async_exchange_publish_with_cloud_event_json(
    aio_pika_mocks: SimpleNamespace,
) -> None:
    pipe = PublishPipeline()
    pipe._publisher = RabbitMQPublisher()
    pipe._connected = False

    spider = MagicMock()
    item = _sample_item()
    out = await pipe.process_item(item, spider)

    assert out is item
    aio_pika_mocks.connect_robust.assert_awaited_once()
    aio_pika_mocks.channel.declare_exchange.assert_awaited_once()
    aio_pika_mocks.exchange.publish.assert_awaited_once()

    call_kw = aio_pika_mocks.exchange.publish.call_args.kwargs
    assert call_kw["routing_key"] == settings.RABBITMQ_ROUTING_KEY
    assert call_kw["mandatory"] is settings.RABBITMQ_PUBLISH_MANDATORY

    msg = aio_pika_mocks.exchange.publish.call_args.args[0]
    payload = orjson.loads(msg.body)

    assert payload["specversion"] == "1.0"
    assert payload["type"] == "com.moscraper.listing.scraped"
    assert payload["datacontenttype"] == "application/json"
    assert payload["subject"] == "listing"
    assert payload["source"] == "moscraper://mediapark"
    assert payload["data"]["title"] == "Phone"
    assert payload["data"]["entity_key"] == "mediapark:1"
    assert payload["data"]["price_value"] == 10


@pytest.mark.asyncio
async def test_publish_pipeline_skips_without_normalized_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipe = PublishPipeline()
    pipe._publisher = AsyncMock()
    pipe._connected = True

    caplog.set_level(logging.WARNING)
    spider = MagicMock()
    item = {"url": "https://example.com/x", "_normalized": None}
    out = await pipe.process_item(item, spider)

    assert out is item
    pipe._publisher.publish_listing_scraped.assert_not_called()
    assert "[PUBLISH_SKIP]" in caplog.text


@pytest.mark.asyncio
async def test_publish_pipeline_broker_publish_failure_logs_and_raises(
    aio_pika_mocks: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    aio_pika_mocks.exchange.publish.side_effect = RuntimeError("broker rejected")

    caplog.set_level(logging.ERROR, logger="infrastructure.publishers.rabbitmq_publisher")

    pipe = PublishPipeline()
    pipe._publisher = RabbitMQPublisher()
    pipe._connected = False
    spider = MagicMock()

    with pytest.raises(RuntimeError, match="broker rejected"):
        await pipe.process_item(_sample_item(), spider)

    assert "RabbitMQ publish failed" in caplog.text
    assert "mediapark:1" in caplog.text


@pytest.mark.asyncio
async def test_publish_pipeline_uses_publisher_mock_without_aio_pika() -> None:
    """Lightweight path: pipeline delegates serialization to RabbitMQPublisher via publish_listing_scraped."""
    pipe = PublishPipeline()
    pub = AsyncMock()
    pipe._publisher = pub
    pipe._connected = True

    spider = MagicMock()
    await pipe.process_item(_sample_item(), spider)

    pub.publish_listing_scraped.assert_awaited_once()
    event = pub.publish_listing_scraped.call_args[0][0]
    assert event.type == "com.moscraper.listing.scraped"
    assert event.data.entity_key == "mediapark:1"
