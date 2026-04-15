from __future__ import annotations

import asyncio
import logging

import aio_pika
import orjson
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.exceptions import (
    AMQPConnectionError,
    ChannelClosed,
    ChannelInvalidStateError,
    ConnectionClosed,
)

from domain.publication_event import ScraperProductEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_publisher_event
from services.publisher.config import PublisherServiceConfig

logger = logging.getLogger(__name__)

_RECOVERABLE_PUBLISH_EXCEPTIONS = (
    AMQPConnectionError,
    ConnectionClosed,
    ChannelClosed,
    ChannelInvalidStateError,
    OSError,
    asyncio.TimeoutError,
)


class RabbitMQPublisher:
    def __init__(self, *, config: PublisherServiceConfig | None = None) -> None:
        self._config = config or PublisherServiceConfig.from_settings()
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None

    async def _close_safely(self, resource) -> None:
        if resource is None:
            return
        try:
            await resource.close()
        except Exception:  # noqa: BLE001
            logger.debug("publisher_transport_close_failed", exc_info=True)

    def _connection_ready(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    def _channel_ready(self) -> bool:
        return self._channel is not None and not self._channel.is_closed

    async def _invalidate_transport(self) -> None:
        exchange = self._exchange
        queue = self._queue
        channel = self._channel
        connection = self._connection
        self._exchange = None
        self._queue = None
        self._channel = None
        self._connection = None

        # Queues/exchanges are channel-scoped; closing the channel/connection is enough.
        del exchange, queue
        await self._close_safely(channel)
        await self._close_safely(connection)

    async def _resolve_exchange(self) -> None:
        assert self._channel is not None
        if self._config.declare_topology:
            await self._ensure_topology()
            return
        self._exchange = await self._channel.get_exchange(self._config.exchange_name, ensure=False)

    async def connect(self) -> None:
        try:
            if not self._connection_ready():
                await self._invalidate_transport()
                client_properties = {"connection_name": self._config.connection_name}
                self._connection = await aio_pika.connect_robust(
                    self._config.rabbitmq_url,
                    heartbeat=self._config.heartbeat_seconds,
                    client_properties=client_properties,
                )
            if not self._channel_ready():
                assert self._connection is not None
                self._channel = await self._connection.channel(publisher_confirms=True)
                self._exchange = None
                self._queue = None
            if self._exchange is None:
                await self._resolve_exchange()
                return
        except Exception as exc:  # noqa: BLE001
            log_publisher_event(
                obs_mc.PUBLISHER_CONNECT_FAILED,
                publisher_service=self._config.publisher_service_name,
                exchange_name=self._config.exchange_name,
                queue_name=self._config.queue_name,
                routing_key=self._config.routing_key,
                severity="error",
                details={
                    "error": str(exc),
                    "connection_name": self._config.connection_name,
                    "declare_topology": self._config.declare_topology,
                },
            )
            raise

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

    async def _publish_once(self, event: ScraperProductEvent) -> None:
        if self._exchange is None:
            await self.connect()
        assert self._exchange is not None
        event.assert_rabbit_publish_contract()
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

    async def publish(self, event: ScraperProductEvent) -> None:
        try:
            await self._publish_once(event)
        except _RECOVERABLE_PUBLISH_EXCEPTIONS as exc:
            log_publisher_event(
                obs_mc.PUBLISHER_PUBLISH_RETRY,
                publisher_service=self._config.publisher_service_name,
                exchange_name=self._config.exchange_name,
                queue_name=self._config.queue_name,
                routing_key=self._config.routing_key,
                event_id=event.event_id,
                store_name=event.store_name,
                scrape_run_id=event.scrape_run_id,
                severity="warning",
                details={
                    "error": str(exc),
                    "attempt_number": event.publication.attempt_number,
                },
            )
            await self._invalidate_transport()
            await self.connect()
            await self._publish_once(event)

    async def close(self) -> None:
        await self._invalidate_transport()
