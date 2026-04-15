from __future__ import annotations

import math
import logging
from urllib.parse import urlparse

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import settings as app_settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.backoff_engine import (
    ExplicitBackoffEngine,
    RateLimitHeaderSnapshot,
)
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

logger = logging.getLogger(__name__)


class ExponentialRetryMiddleware(RetryMiddleware):
    RETRY_HTTP_CODES = {429, 503, 520, 521, 522}
    MAX_RETRY_TIMES = 5

    def __init__(self, settings):
        super().__init__(settings)
        self.retry_http_codes = self.RETRY_HTTP_CODES
        self._backoff_engine = ExplicitBackoffEngine.from_settings(app_settings)

    @staticmethod
    def _is_monitoring_enabled(store: str) -> bool:
        if not getattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False):
            return False
        return is_feature_enabled("ban_signal_monitoring", store)

    @staticmethod
    def _is_explicit_backoff_enabled(store: str) -> bool:
        if not getattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", False):
            return False
        return is_feature_enabled("explicit_backoff_engine", store)

    @staticmethod
    def _is_explicit_backoff_enforce_enabled(store: str) -> bool:
        if not getattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", False):
            return False
        allowlist = tuple(
            str(name).strip().lower()
            for name in (getattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", []) or [])
            if str(name).strip()
        )
        if allowlist and (store or "").strip().lower() not in set(allowlist):
            return False
        return is_feature_enabled("explicit_backoff_enforcement", store)

    def process_response(self, request, response, spider):
        if request.meta.get("dont_retry", False):
            return response
        if response.status not in self.retry_http_codes:
            return response

        store = str(request.meta.get("store_name") or getattr(spider, "store_name", "") or spider.name)
        domain = (urlparse(request.url).netloc or "").strip().lower()
        retry_times = int(request.meta.get("retry_times", 0))
        backoff_decision = None
        if self._is_explicit_backoff_enabled(store) and self._backoff_engine.supports_status(int(response.status)):
            header_snapshot = RateLimitHeaderSnapshot()
            if bool(getattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)):
                header_snapshot = self._backoff_engine.parse_headers(response.headers)
            backoff_decision = self._backoff_engine.classify(
                status=int(response.status),
                prior_failures=retry_times,
                headers_snapshot=header_snapshot,
            )
            request.meta.setdefault("access_backoff_reason", backoff_decision.reason)
            request.meta.setdefault("access_backoff_wait_seconds", round(backoff_decision.wait_seconds, 3))
            request.meta.setdefault(
                "access_backoff_cooldown_seconds",
                round(backoff_decision.cooldown_seconds, 3),
            )
            if backoff_decision.actions:
                request.meta.setdefault("access_backoff_actions", list(backoff_decision.actions))
        retry_reason = str(
            request.meta.get("retry_reason")
            or request.meta.get("access_backoff_reason")
            or request.meta.get("access_last_signal")
            or f"http_{int(response.status)}"
        )
        if self._is_monitoring_enabled(store):
            access_metrics.bump("retry_http_total")
            access_metrics.bump("retries_by_reason_total")
            access_metrics.bump_labeled(
                "retries_by_reason_total",
                store=store,
                domain=domain,
                reason=retry_reason,
                status=int(response.status),
            )

        if retry_times >= self.MAX_RETRY_TIMES:
            return response

        enforce_backoff = self._is_explicit_backoff_enforce_enabled(store)
        if enforce_backoff and backoff_decision is not None and not backoff_decision.retry_allowed:
            access_metrics.bump("explicit_backoff_retry_blocked_total")
            request.meta["access_backoff_retry_blocked"] = True
            logger.info(
                "[RETRY_BLOCKED] %s status=%d reason=%s",
                request.url,
                response.status,
                backoff_decision.reason,
            )
            return response

        wait = 2**retry_times
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = int(retry_after)
                except (ValueError, TypeError):
                    pass
        if enforce_backoff and backoff_decision is not None and backoff_decision.wait_seconds > 0.0:
            explicit_wait = int(math.ceil(float(backoff_decision.wait_seconds)))
            if explicit_wait > wait:
                wait = explicit_wait
            access_metrics.bump("explicit_backoff_wait_applied_total")
            request.meta["access_backoff_wait_applied"] = wait

        logger.warning(
            "[RETRY] %s status=%d retry=%d wait=%ds signal=%s solver=%s backoff=%s backoff_wait=%s",
            request.url,
            response.status,
            retry_times,
            wait,
            request.meta.get("access_last_signal"),
            request.meta.get("captcha_solver_name"),
            request.meta.get("access_backoff_reason"),
            request.meta.get("access_backoff_wait_seconds"),
        )

        reason = response_status_message(response.status)
        retried = self._retry(request, reason)
        if retried is not None:
            retried.meta["download_timeout"] = wait + 10
            retried.meta["retry_reason"] = retry_reason
            if request.meta.get("captcha_solver_name"):
                retried.meta["captcha_solver_name"] = request.meta.get("captcha_solver_name")
            if request.meta.get("access_backoff_reason"):
                retried.meta["access_backoff_reason"] = request.meta.get("access_backoff_reason")
            if request.meta.get("access_backoff_wait_seconds") is not None:
                retried.meta["access_backoff_wait_seconds"] = request.meta.get("access_backoff_wait_seconds")
            if request.meta.get("access_backoff_cooldown_seconds") is not None:
                retried.meta["access_backoff_cooldown_seconds"] = request.meta.get(
                    "access_backoff_cooldown_seconds"
                )
        return retried or response
