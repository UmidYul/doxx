from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from domain.publication_event import ScraperProductEvent
from infrastructure.persistence.sqlite_store import ClaimedOutboxMessage
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import SQLiteOutboxReader
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
        outbox_reader: SQLiteOutboxReader | None = None,
        rabbit_publisher: RabbitMQPublisher | None = None,
    ) -> None:
        self._config = config or PublisherServiceConfig.from_settings()
        self._outbox_reader = outbox_reader or SQLiteOutboxReader(config=self._config)
        self._rabbit_publisher = rabbit_publisher or RabbitMQPublisher(config=self._config)

    def _build_delivery_event(self, message: ClaimedOutboxMessage) -> ScraperProductEvent:
        publication = message.payload.publication.model_copy(
            update={
                "publication_version": message.payload.publication.publication_version,
                "exchange_name": self._config.exchange_name,
                "queue_name": self._config.queue_name,
                "routing_key": self._config.routing_key,
                "outbox_status": "publishing",
                "attempt_number": message.attempt_count + 1,
                "publisher_service": self._config.publisher_service_name,
                "published_at": None,
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
        messages = self._outbox_reader.claim_batch()
        result = PublicationRunResult(claimed=len(messages))
        if not messages:
            return result

        await self._rabbit_publisher.connect()
        for message in messages:
            delivery_event = self._build_delivery_event(message)
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
                logger.exception(
                    "publisher_publish_failed event_id=%s retryable=%s",
                    message.event_id,
                    retryable,
                )
                continue

            self._outbox_reader.mark_published(event_id=message.event_id)
            result.published += 1
        return result

    async def run_forever(self) -> None:
        while True:
            result = await self.run_once()
            if result.claimed == 0:
                await asyncio.sleep(self._config.poll_interval_seconds)

    async def aclose(self) -> None:
        await self._rabbit_publisher.close()
        self._outbox_reader.close()
