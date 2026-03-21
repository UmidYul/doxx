from __future__ import annotations

import logging

from fake_useragent import UserAgent

logger = logging.getLogger(__name__)


class MobileRedirectMiddleware:
    def __init__(self):
        try:
            self.ua = UserAgent()
        except Exception:
            self.ua = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        response_host = response.url.split("/")[2] if "/" in response.url else ""
        request_host = request.url.split("/")[2] if "/" in request.url else ""

        if response_host.startswith("m.") and not request_host.startswith("m."):
            if request.meta.get("_mobile_retry"):
                return response  # already retried once

            logger.warning(
                "[MOBILE_REDIRECT] %s → %s, retrying with desktop UA",
                request.url,
                response.url,
            )
            desktop_ua = (
                self.ua.chrome
                if self.ua
                else (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            new_request = request.copy()
            new_request.headers[b"User-Agent"] = (
                desktop_ua.encode() if isinstance(desktop_ua, str) else desktop_ua
            )
            new_request.meta["_mobile_retry"] = True
            new_request.dont_filter = True
            return new_request

        return response
