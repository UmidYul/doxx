from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config.settings import settings
from infrastructure.publishers.base import MessagePublisher
from infrastructure.publishers.rabbitmq_publisher import RabbitMQPublisher

if TYPE_CHECKING:
    from domain.messages import CloudEventListingScraped

logger = logging.getLogger(__name__)


class _DisabledPublisher(MessagePublisher):
    async def publish_listing_scraped(self, event: CloudEventListingScraped) -> None:
        logger.debug("MOSCRAPER_DISABLE_PUBLISH: skip publish id=%s", event.id)


def get_publisher() -> MessagePublisher:
    if settings.MOSCRAPER_DISABLE_PUBLISH:
        return _DisabledPublisher()
    if settings.BROKER_TYPE.lower() != "rabbitmq":
        raise ValueError(f"Unsupported BROKER_TYPE: {settings.BROKER_TYPE!r}")
    return RabbitMQPublisher()
