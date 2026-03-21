from __future__ import annotations

import logging

from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

logger = logging.getLogger(__name__)


class ExponentialRetryMiddleware(RetryMiddleware):
    RETRY_HTTP_CODES = {429, 503, 520, 521, 522}
    MAX_RETRY_TIMES = 5

    def __init__(self, settings):
        super().__init__(settings)
        self.retry_http_codes = self.RETRY_HTTP_CODES

    def process_response(self, request, response, spider):
        if request.meta.get("dont_retry", False):
            return response
        if response.status not in self.retry_http_codes:
            return response

        retry_times = request.meta.get("retry_times", 0)
        if retry_times >= self.MAX_RETRY_TIMES:
            return response

        wait = 2**retry_times
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = int(retry_after)
                except (ValueError, TypeError):
                    pass

        logger.warning(
            "[RETRY] %s status=%d retry=%d wait=%ds",
            request.url,
            response.status,
            retry_times,
            wait,
        )

        reason = response_status_message(response.status)
        retried = self._retry(request, reason)
        if retried is not None:
            retried.meta["download_timeout"] = wait + 10
        return retried or response
