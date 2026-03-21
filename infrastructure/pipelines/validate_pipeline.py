from __future__ import annotations

import logging

from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ValidatePipeline:
    def process_item(self, item, spider):
        if "discovered_url" in item:
            return item  # discovery items pass through
        if not item.get("title") and not item.get("name"):
            logger.warning("[VALIDATE_DROP] Missing title: %s", item.get("url", "unknown"))
            raise DropItem("Missing title")
        if not item.get("url"):
            logger.warning("[VALIDATE_DROP] Missing URL")
            raise DropItem("Missing URL")
        return item
