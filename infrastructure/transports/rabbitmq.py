from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.crm_apply_result import CrmApplyResult
from infrastructure.transports.base import BaseTransport

if TYPE_CHECKING:
    from domain.parser_event import ParserSyncEvent

logger = logging.getLogger(__name__)


class RabbitMQTransport(BaseTransport):
    """Legacy adapter: publishes ``event.data`` as CloudEvent."""

    def __init__(self) -> None:
        self._publisher = None

    async def _ensure_publisher(self) -> None:
        if self._publisher is not None:
            return
        from infrastructure.publishers.rabbitmq_publisher import RabbitMQPublisher

        self._publisher = RabbitMQPublisher()
        await self._publisher.connect()

    async def send_one_event(self, event: ParserSyncEvent) -> CrmApplyResult:
        await self._ensure_publisher()
        item = event.data

        from application.message_builder import build_listing_event

        ev = build_listing_event(
            store=item.source_name,
            url=item.source_url,
            title=item.title,
            scraped_at=item.scraped_at,
            source_id=item.source_id,
            price_raw=item.price_raw,
            price_value=item.price_value,
            currency=item.currency,
            in_stock=item.in_stock,
            brand=item.brand,
            raw_specs=dict(item.raw_specs),
            description=item.description,
            image_urls=list(item.image_urls),
        )
        await self._publisher.publish_listing_scraped(ev)
        logger.debug(
            "[RABBITMQ_OK] entity_key=%s event_id=%s",
            item.entity_key,
            ev.id,
        )
        return CrmApplyResult(
            event_id=event.event_id,
            entity_key=item.entity_key,
            payload_hash=event.payload_hash,
            success=True,
            status="applied",
            http_status=200,
            action="published",
        )

    async def close(self) -> None:
        if self._publisher:
            await self._publisher.close()
            self._publisher = None
