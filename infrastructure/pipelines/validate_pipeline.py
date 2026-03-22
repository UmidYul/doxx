from __future__ import annotations

import logging

from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


def _safe_bool(value: Any) -> bool:
    """Convert truthy/falsy values without the ``bool("false") == True`` trap."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "нет", "none", "")
    return True


class ValidatePipeline:
    """Drop items missing required fields; coerce ``raw_specs`` / ``image_urls`` shapes.

    ``in_stock`` is left as-is (no ``bool(str)``); :class:`NormalizePipeline` applies
    ``normalize_stock_value``.
    """

    def process_item(self, item, spider):
        url = item.get("url", "")

        if not item.get("title") and not item.get("name"):
            logger.warning("[VALIDATE_DROP] Missing title: %s", url or "unknown")
            raise DropItem("Missing title")

        if not url:
            logger.warning("[VALIDATE_DROP] Missing URL")
            raise DropItem("Missing URL")

        store = item.get("source") or getattr(spider, "store_name", None)
        if not store:
            logger.warning("[VALIDATE_DROP] Missing source/store: %s", url)
            raise DropItem("Missing source/store")
        item["source"] = store

        if not item.get("source_id") and not url:
            logger.warning("[VALIDATE_DROP] Missing identifier (source_id or url): %s", url)
            raise DropItem("Missing identifier")

        # in_stock: do not use bool(...) on strings — NormalizePipeline uses normalize_stock_value

        raw_specs = item.get("raw_specs")
        if isinstance(raw_specs, dict):
            item["raw_specs"] = {str(k): v for k, v in raw_specs.items()}
        else:
            item["raw_specs"] = {}

        imgs = item.get("image_urls")
        if isinstance(imgs, list):
            item["image_urls"] = [str(u).strip() for u in imgs if u]
        else:
            item["image_urls"] = []

        price_str = str(item.get("price_str") or "").strip()
        if not price_str:
            logger.warning("[VALIDATE_WARN] No price for %s", url)

        return item
