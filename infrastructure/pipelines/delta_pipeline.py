from __future__ import annotations

import asyncio
import logging

from application.delta_detector import DeltaDetector
from application.event_sender import EventSender
from infrastructure.db.parse_cache_repo import ParseCacheRepo
from infrastructure.db.store_repo import StoreRepo

logger = logging.getLogger(__name__)


class DeltaPipeline:
    def __init__(self) -> None:
        self.delta_detector = None
        self.event_sender = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        self.delta_detector = DeltaDetector()
        self.event_sender = EventSender()

    async def process_item(self, item, spider):
        if "discovered_url" in item:
            return item

        normalized = item.get("_normalized")
        if not normalized:
            return item

        store_repo = StoreRepo()
        raw_row = {
            "name": normalized.name,
            "price": float(normalized.price) if normalized.price is not None else None,
            "in_stock": normalized.in_stock,
            "url": normalized.url,
            "characteristics": item.get("raw_specs") or {},
            "images": item.get("image_urls") or [],
        }
        if item.get("raw_html") is not None:
            raw_row["raw_html"] = item["raw_html"]

        try:
            await asyncio.to_thread(store_repo.upsert_product, normalized.source, raw_row)
        except Exception:
            logger.exception("[DELTA] store upsert failed url=%s", normalized.url)

        repo = ParseCacheRepo()
        cache = await repo.get_by_url(normalized.url)

        events = self.delta_detector.detect(normalized, cache)

        if not events:
            spider.logger.debug("[DELTA_EMPTY] %s", normalized.url)
            return item

        crm_listing_id = cache.crm_listing_id if cache else None
        crm_product_id = cache.crm_product_id if cache else None

        for event in events:
            success, crm_response = await self.event_sender.send_event_detail(event)
            if success:
                spider.logger.info("[CRM_SYNC] %s for %s", event.event, normalized.url)
                if crm_response:
                    if crm_response.crm_listing_id is not None:
                        crm_listing_id = crm_response.crm_listing_id
                    if crm_response.crm_product_id is not None:
                        crm_product_id = crm_response.crm_product_id
                await repo.upsert(
                    url=normalized.url,
                    source_name=normalized.source,
                    source_id=normalized.source_id or None,
                    price=normalized.price,
                    in_stock=normalized.in_stock,
                    crm_listing_id=crm_listing_id,
                    crm_product_id=crm_product_id,
                )
                await repo.mark_parsed(normalized.url)

        return item
