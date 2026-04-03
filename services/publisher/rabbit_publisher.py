from __future__ import annotations

import logging

import aio_pika
import orjson
from aio_pika import DeliveryMode, ExchangeType

from domain.publication_event import ScraperProductEvent
from services.publisher.config import PublisherServiceConfig

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    def __init__(self, *, config: PublisherServiceConfig | None = None) -> None:
        self._config = config or PublisherServiceConfig.from_settings()
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        self._connection = await aio_pika.connect_robust(self._config.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._ensure_topology()

    async def _ensure_topology(self) -> None:
        assert self._channel is not None
        exchange_type = {
            "topic": ExchangeType.TOPIC,
            "direct": ExchangeType.DIRECT,
            "fanout": ExchangeType.FANOUT,
            "headers": ExchangeType.HEADERS,
        }.get(self._config.exchange_type.lower(), ExchangeType.TOPIC)
        self._exchange = await self._channel.declare_exchange(
            self._config.exchange_name,
            exchange_type,
            durable=True,
        )
        self._queue = await self._channel.declare_queue(
            self._config.queue_name,
            durable=True,
        )
        await self._queue.bind(self._exchange, routing_key=self._config.routing_key)

    async def publish(self, event: ScraperProductEvent) -> None:
        if self._exchange is None:
            await self.connect()
        assert self._exchange is not None
        body = orjson.dumps(event.model_dump(mode="json", by_alias=True))
        message = aio_pika.Message(
            body=body,
            message_id=event.event_id,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            type=event.event_type,
            headers={
                "schema_version": event.schema_version,
                "store_name": event.store_name,
                "scrape_run_id": event.scrape_run_id,
                "payload_hash": event.payload_hash,
            },
        )
        await self._exchange.publish(
            message,
            routing_key=self._config.routing_key,
            mandatory=self._config.publish_mandatory,
        )
        logger.info(
            "publisher_rabbit_published exchange=%s queue=%s routing_key=%s event_id=%s",
            self._config.exchange_name,
            self._config.queue_name,
            self._config.routing_key,
            event.event_id,
        )

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
        self._exchange = None
        self._queue = None
