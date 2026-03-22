from __future__ import annotations

from typing import Any

import scrapy.http

from infrastructure.spiders.base import BaseProductSpider

_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"


class UzumSpider(BaseProductSpider):
    """UZUM marketplace (heavy JS). **Opt-in browser:** install ``pip install '.[playwright]'`` then ``playwright install``.

    Listing → PDP extraction is **TBD**; this spider uses the shared crawl framework and seeds the homepage
    so the contract stays consistent across stores.
    """

    name = "uzum"
    store_name = "uzum"
    allowed_domains = ["uzum.uz"]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_HANDLERS": {
            "https": _PLAYWRIGHT_HANDLER,
            "http": _PLAYWRIGHT_HANDLER,
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "CONCURRENT_REQUESTS": 4,
        "DOWNLOAD_DELAY": 1.0,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        return ("https://uzum.uz/",)

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return False

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        return []

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        return None

    def extract_source_id_from_url(self, url: str) -> str | None:
        return None

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        return None
