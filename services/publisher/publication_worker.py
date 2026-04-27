from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.publication_event import ScraperProductEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_publisher_event
from infrastructure.persistence.base import ClaimedOutboxMessage
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import PersistenceOutboxReader
from services.publisher.rabbit_publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublicationRunResult:
    claimed: int = 0
    published: int = 0
    failed: int = 0


class PublicationWorker:
    def __init__(
        self,
        *,
        config: PublisherServiceConfig | None = None,
        outbox_reader: PersistenceOutboxReader | None = None,
        rabbit_publisher: RabbitMQPublisher | None = None,
    ) -> None:
        self._config = config or PublisherServiceConfig.from_settings()
        self._outbox_reader = outbox_reader or PersistenceOutboxReader(config=self._config)
        self._rabbit_publisher = rabbit_publisher or RabbitMQPublisher(config=self._config)

    def _build_delivery_event(
        self,
        message: ClaimedOutboxMessage,
        *,
        published_at: datetime,
    ) -> ScraperProductEvent:
        publication = message.payload.publication.model_copy(
            update={
                "publication_version": message.payload.publication.publication_version,
                "exchange_name": self._config.exchange_name,
                "queue_name": self._config.queue_name,
                "routing_key": self._config.routing_key,
                "outbox_status": "published",
                "attempt_number": message.attempt_count + 1,
                "publisher_service": self._config.publisher_service_name,
                "published_at": published_at,
            }
        )
        return message.payload.model_copy(
            update={
                "schema_version": message.payload.schema_version,
                "publication": publication,
            }
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        return not isinstance(exc, (TypeError, ValueError))

    async def run_once(self) -> PublicationRunResult:
        result = PublicationRunResult()
        if not self._outbox_reader.has_claimable_messages():
            return result

        await self._rabbit_publisher.connect()
        messages = self._outbox_reader.claim_batch()
        result.claimed = len(messages)
        if not messages:
            return result

        for message in messages:
            published_at = datetime.now(UTC)
            delivery_event = self._build_delivery_event(message, published_at=published_at)
            try:
                await self._rabbit_publisher.publish(delivery_event)
            except Exception as exc:  # noqa: BLE001
                retryable = self._is_retryable(exc)
                self._outbox_reader.mark_failed(
                    event_id=message.event_id,
                    error_message=str(exc),
                    retryable=retryable,
                )
                result.failed += 1
                log_publisher_event(
                    obs_mc.PUBLISHER_MESSAGE_FAILED,
                    publisher_service=self._config.publisher_service_name,
                    exchange_name=self._config.exchange_name,
                    queue_name=self._config.queue_name,
                    routing_key=self._config.routing_key,
                    event_id=message.event_id,
                    store_name=message.payload.store_name,
                    scrape_run_id=message.payload.scrape_run_id,
                    severity="warning" if retryable else "error",
                    details={
                        "error": str(exc),
                        "retryable": retryable,
                        "attempt_number": message.attempt_count + 1,
                    },
                )
                logger.exception(
                    "publisher_publish_failed event_id=%s retryable=%s",
                    message.event_id,
                    retryable,
                )
                continue

            self._outbox_reader.mark_published(event_id=message.event_id, published_event=delivery_event)
            result.published += 1
        log_publisher_event(
            obs_mc.PUBLISHER_BATCH_COMPLETED,
            publisher_service=self._config.publisher_service_name,
            exchange_name=self._config.exchange_name,
            queue_name=self._config.queue_name,
            routing_key=self._config.routing_key,
            claimed=result.claimed,
            published=result.published,
            failed=result.failed,
            details={"batch_size": self._config.batch_size},
        )
        return result

    async def run_forever(self) -> None:
        while True:
            try:
                result = await self.run_once()
            except Exception as exc:  # noqa: BLE001
                log_publisher_event(
                    obs_mc.PUBLISHER_RUN_FAILED,
                    publisher_service=self._config.publisher_service_name,
                    exchange_name=self._config.exchange_name,
                    queue_name=self._config.queue_name,
                    routing_key=self._config.routing_key,
                    severity="error",
                    details={"error": str(exc)},
                )
                logger.exception("publisher_run_once_failed")
                await asyncio.sleep(self._config.poll_interval_seconds)
                continue
            if result.claimed == 0:
                await asyncio.sleep(self._config.poll_interval_seconds)

    async def aclose(self) -> None:
        try:
            await self._rabbit_publisher.close()
        finally:
            self._outbox_reader.close()
