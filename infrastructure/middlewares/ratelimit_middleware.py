from __future__ import annotations

import logging
import time
from collections import deque
from statistics import median

from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


class AdaptiveRateLimitMiddleware:
    def __init__(self):
        self.response_times: dict[str, deque[float]] = {}  # domain → deque(maxlen=10)
        self.download_delays: dict[str, float] = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        request.meta["_request_start"] = time.monotonic()

    def process_response(self, request, response, spider):
        domain = request.url.split("/")[2] if "/" in request.url else ""

        # Track response time
        start = request.meta.get("_request_start")
        if start is not None:
            elapsed = time.monotonic() - start
            if domain not in self.response_times:
                self.response_times[domain] = deque(maxlen=10)
            self.response_times[domain].append(elapsed)

            # If latest > 3x median: increase delay
            times = self.response_times[domain]
            if len(times) >= 3:
                med = median(times)
                if elapsed > 3 * med:
                    current_delay = self.download_delays.get(
                        domain, spider.settings.getfloat("DOWNLOAD_DELAY", 1.0)
                    )
                    new_delay = min(current_delay * 1.5, 30.0)
                    self.download_delays[domain] = new_delay
                    spider.download_delay = new_delay
                    logger.warning(
                        "[RATE_LIMIT_SUSPECTED] %s delay: %.1f → %.1f",
                        domain,
                        current_delay,
                        new_delay,
                    )

        # Empty body check
        if response.status == 200 and len(response.body) < 500:
            logger.warning("[EMPTY_BODY_200] %s (%d bytes)", request.url, len(response.body))
            raise IgnoreRequest(f"Empty body: {len(response.body)} bytes")

        return response
