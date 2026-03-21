from __future__ import annotations

from typing import Any

import scrapy

from infrastructure.spiders.base import BaseProductSpider

_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"


class UzumSpider(BaseProductSpider):
    """UZUM marketplace (heavy JS). **Opt-in browser:** install ``pip install '.[playwright]'`` then ``playwright install``.

    Only this spider registers ``scrapy-playwright`` download handlers; all other spiders use plain TCP/HTTP.
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

    def start_requests(self):
        yield scrapy.Request(
            "https://uzum.uz/",
            callback=self.parse,
            meta={"playwright": True},
            errback=self.errback_default,
        )

    def parse(self, response: scrapy.http.Response):
        self.logger.info("[UZUM] Playwright fetch ok url=%s bytes=%s", response.url, len(response.body))
        # Stub: listing → PDP extraction TBD; no items until implemented.

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        return None
