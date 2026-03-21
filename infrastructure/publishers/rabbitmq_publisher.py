from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aio_pika
import orjson
from aio_pika import DeliveryMode, ExchangeType

from config.settings import settings
from infrastructure.publishers.base import MessagePublisher

if TYPE_CHECKING:
    from domain.messages import CloudEventListingScraped

logger = logging.getLogger(__name__)


class RabbitMQPublisher(MessagePublisher):
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        if self._exchange is not None:
            return
        try:
            self._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self._channel = await self._connection.channel(publisher_confirms=True)
            _map = {
                "topic": ExchangeType.TOPIC,
                "direct": ExchangeType.DIRECT,
                "fanout": ExchangeType.FANOUT,
                "headers": ExchangeType.HEADERS,
            }
            ex_type = _map.get(settings.RABBITMQ_EXCHANGE_TYPE.lower(), ExchangeType.TOPIC)
            self._exchange = await self._channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE,
                ex_type,
                durable=True,
            )
        except Exception as e:
            logger.exception("RabbitMQ connect failed (exchange=%s)", settings.RABBITMQ_EXCHANGE)
            raise ConnectionError(
                "Moscraper could not connect to RabbitMQ; check RABBITMQ_URL and that the broker is running."
            ) from e
        logger.info(
            "RabbitMQ publisher ready exchange=%s type=%s",
            settings.RABBITMQ_EXCHANGE,
            settings.RABBITMQ_EXCHANGE_TYPE,
        )

    async def publish_listing_scraped(self, event: CloudEventListingScraped) -> None:
        if self._exchange is None:
            await self.connect()
        assert self._exchange is not None
        body = orjson.dumps(event.model_dump(mode="json"))
        msg = aio_pika.Message(
            body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        try:
            await self._exchange.publish(
                msg,
                routing_key=settings.RABBITMQ_ROUTING_KEY,
                mandatory=settings.RABBITMQ_PUBLISH_MANDATORY,
            )
        except Exception:
            logger.exception(
                "RabbitMQ publish failed routing_key=%s entity_key=%s event_id=%s",
                settings.RABBITMQ_ROUTING_KEY,
                event.data.entity_key,
                event.id,
            )
            raise

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None
        if self._connection:
            await self._connection.close()
            self._connection = None
        self._exchange = None
