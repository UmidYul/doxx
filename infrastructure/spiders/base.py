from __future__ import annotations

import hashlib
from typing import Any

import scrapy

from domain.raw_product import as_scrapy_item_dict


class BaseProductSpider(scrapy.Spider):
    store_name: str = ""

    # Default: lightweight HTTP. For SPA/JS-heavy sites, override custom_settings
    # with scrapy-playwright download handlers + request meta (install optional extra `.[playwright]`).
    custom_settings = {
        "DOWNLOAD_DELAY": 1.0,
    }

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        raise NotImplementedError

    def parse(self, response: scrapy.http.Response):
        """Default: one response → one item. Store spiders usually override for listing → PDP."""
        item = self.full_parse_item(response)
        if item:
            item.setdefault("source", self.store_name)
            item.setdefault("url", response.url)
            yield as_scrapy_item_dict(item)

    def _zero_result_guard(self, urls: list[str], response: scrapy.http.Response) -> None:
        if not urls and response.meta.get("page", 1) == 1:
            self.logger.warning("[ZERO_RESULT] %s", response.url)

    def _is_duplicate_page(self, response: scrapy.http.Response, _next_url: str = "") -> bool:
        """In-process duplicate page guard (hash set per crawl, no Redis)."""
        items = response.css(".product-card::text").getall()[:5]
        page_hash = hashlib.md5("".join(items).encode()).hexdigest()
        if not hasattr(self, "_seen_page_hashes"):
            self._seen_page_hashes = set()
        if page_hash in self._seen_page_hashes:
            self.logger.warning("[DUPLICATE_PAGE] %s hash=%s", response.url, page_hash)
            return True
        self._seen_page_hashes.add(page_hash)
        return False

    def errback_default(self, failure):
        self.logger.error("[SPIDER_ERROR] %s: %s", failure.request.url, failure.getErrorMessage())
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(failure.value)
        except ImportError:
            pass
