from __future__ import annotations

import logging

from application.message_builder import build_listing_event
from infrastructure.publishers.publisher_factory import get_publisher

logger = logging.getLogger(__name__)


class PublishPipeline:
    """Publish normalized listings to RabbitMQ as CloudEvents (``orjson`` + **aio-pika**, publisher confirms).

    Uses :class:`~infrastructure.publishers.rabbitmq_publisher.RabbitMQPublisher` (topic exchange by default).
    On broker failure the crawl fails fast (no local backlog); see ``MOSCRAPER_DISABLE_PUBLISH`` for tests.
    """

    def __init__(self) -> None:
        self._publisher = None
        self._connected = False

    @classmethod
    def from_crawler(cls, _crawler):
        return cls()

    def open_spider(self, spider):
        self._publisher = get_publisher()
        self._connected = False

    async def close_spider(self, spider):
        if self._publisher and hasattr(self._publisher, "close"):
            await self._publisher.close()
        self._publisher = None
        self._connected = False

    async def process_item(self, item, spider):
        if self._publisher is None:
            raise RuntimeError("PublishPipeline: publisher not initialized")
        if not self._connected and hasattr(self._publisher, "connect"):
            await self._publisher.connect()
            self._connected = True

        norm = item.get("_normalized")
        if not norm:
            logger.warning("[PUBLISH_SKIP] missing _normalized url=%s", item.get("url"))
            return item

        price_f = norm.get("price")
        price_value = int(round(price_f)) if price_f is not None else None

        event = build_listing_event(
            store=norm["store"],
            url=norm["url"],
            title=norm["title"],
            source_id=norm.get("source_id"),
            price_raw=norm.get("price_raw"),
            price_value=price_value,
            currency=norm.get("currency"),
            in_stock=norm.get("in_stock"),
            brand=norm.get("brand"),
            raw_specs=norm.get("raw_specs"),
            description=norm.get("description"),
            image_urls=norm.get("image_urls"),
        )
        await self._publisher.publish_listing_scraped(event)
        logger.debug("[PUBLISH_OK] %s %s", event.data.entity_key, event.id)
        return item
