from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import orjson
import pytest

from application.message_builder import build_listing_event
from infrastructure.publishers.rabbitmq_publisher import RabbitMQPublisher


@pytest.mark.asyncio
async def test_publish_uses_orjson_body_matching_event_dump():
    publisher = RabbitMQPublisher()
    publisher._exchange = AsyncMock()

    when = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)
    event = build_listing_event(
        store="mediapark",
        url="https://mediapark.uz/p",
        title="Phone",
        scraped_at=when,
        source_id="1",
        price_raw="10",
        price_value=10,
    )
    expected = orjson.dumps(event.model_dump(mode="json"))

    await publisher.publish_listing_scraped(event)

    publisher._exchange.publish.assert_awaited_once()
    msg = publisher._exchange.publish.call_args[0][0]
    assert msg.body == expected
    assert msg.content_type == "application/json"


@pytest.mark.asyncio
async def test_connect_failure_raises_connection_error_with_message():
    publisher = RabbitMQPublisher()
    with patch(
        "infrastructure.publishers.rabbitmq_publisher.aio_pika.connect_robust",
        new_callable=AsyncMock,
        side_effect=OSError(10061, "connection refused"),
    ):
        with pytest.raises(ConnectionError, match="could not connect to RabbitMQ"):
            await publisher.connect()


@pytest.mark.asyncio
async def test_connect_wraps_connection_error_with_cause():
    publisher = RabbitMQPublisher()
    inner = ConnectionError("broker down")
    with patch(
        "infrastructure.publishers.rabbitmq_publisher.aio_pika.connect_robust",
        new_callable=AsyncMock,
        side_effect=inner,
    ):
        with pytest.raises(ConnectionError, match="could not connect to RabbitMQ") as exc:
            await publisher.connect()
    assert exc.value.__cause__ is inner
