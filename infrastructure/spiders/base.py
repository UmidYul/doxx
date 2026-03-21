from __future__ import annotations

import hashlib
from typing import Any

import scrapy


class BaseProductSpider(scrapy.Spider):
    store_name: str = ""
    parse_mode: str = "full"  # "fast", "full", "discover"

    # Default: lightweight HTTP. For SPA/JS-heavy sites, override custom_settings
    # with scrapy-playwright download handlers (install optional extra `.[playwright]`).
    custom_settings = {
        "DOWNLOAD_DELAY": 1.0,
    }

    def fast_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        raise NotImplementedError

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        raise NotImplementedError

    def discover_urls(self, response: scrapy.http.Response) -> list[str]:
        raise NotImplementedError

    def parse(self, response: scrapy.http.Response):
        """Route to appropriate parse method based on parse_mode."""
        if self.parse_mode == "fast":
            yield from self._handle_fast(response)
        elif self.parse_mode == "discover":
            yield from self._handle_discover(response)
        else:
            yield from self._handle_full(response)

    def _handle_fast(self, response: scrapy.http.Response):
        item = self.fast_parse_item(response)
        if item:
            item.setdefault("source", self.store_name)
            item.setdefault("url", response.url)
            yield item

    def _handle_full(self, response: scrapy.http.Response):
        item = self.full_parse_item(response)
        if item:
            item.setdefault("source", self.store_name)
            item.setdefault("url", response.url)
            yield item

    def _handle_discover(self, response: scrapy.http.Response):
        urls = self.discover_urls(response)
        self._zero_result_guard(urls, response)
        for url in urls:
            yield {"discovered_url": url, "source": self.store_name}

    def _zero_result_guard(self, urls: list[str], response: scrapy.http.Response) -> None:
        if not urls and response.meta.get("page", 1) == 1:
            self.logger.warning("[ZERO_RESULT] %s", response.url)

    def _is_duplicate_page(self, response: scrapy.http.Response, _next_url: str = "") -> bool:
        """Bloom-filter-like check using set of page content hashes."""
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
