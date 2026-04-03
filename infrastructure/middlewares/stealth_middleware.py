from __future__ import annotations


class StealthMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        if "playwright" in request.meta:
            request.meta.setdefault("playwright_page_init_callback", self._init_page)

    @staticmethod
    async def _init_page(page, request=None):
        try:
            from playwright_stealth import stealth_async

            await stealth_async(page)
        except ImportError:
            pass
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.set_extra_http_headers(
            {
                "Accept-Language": "ru-RU,ru;q=0.9,uz;q=0.8",
            }
        )
