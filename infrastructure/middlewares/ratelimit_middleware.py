from __future__ import annotations

import json
import logging
import time
from collections import deque
from statistics import median

import scrapy.http

from config.settings import settings as app_settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.ban_detector import detect_ban_signal
from infrastructure.access.header_profiles import build_desktop_headers
from infrastructure.access.request_strategy import (
    build_request_meta,
    should_escalate_to_browser,
    should_escalate_to_proxy,
)
from infrastructure.access.store_profiles import get_store_profile

logger = logging.getLogger(__name__)


def _spider_supports_playwright(spider) -> bool:
    h = spider.settings.get("DOWNLOAD_HANDLERS") or {}
    v = str(h.get("https") or h.get("http") or "")
    return "playwright" in v.lower()


def _access_json(event: str, **fields) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.info("access_layer %s", json.dumps({"event": event, **payload}, default=str, ensure_ascii=False))


class AccessAwareRateLimitMiddleware:
    """Adaptive delay + ban-aware handling (no blind small-body IgnoreRequest)."""

    def __init__(self) -> None:
        self.response_times: dict[str, deque[float]] = {}
        self.download_delays: dict[str, float] = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request: scrapy.http.Request, spider):
        request.meta.setdefault("_request_start", time.monotonic())

    def process_response(
        self,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
    ):
        domain = request.url.split("/")[2] if "/" in request.url else ""

        start = request.meta.get("_request_start")
        if start is not None:
            elapsed = time.monotonic() - float(start)
            if domain not in self.response_times:
                self.response_times[domain] = deque(maxlen=10)
            self.response_times[domain].append(elapsed)
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
                    access_metrics.bump("retry_transport_total")
                    _access_json(
                        "REQUEST_RETRY_CLASSIFIED",
                        spider=spider.name,
                        store=request.meta.get("store_name") or getattr(spider, "store_name", None),
                        purpose=request.meta.get("access_purpose"),
                        url=request.url,
                        reason="slow_origin_backoff",
                        mode="plain",
                        retry_count=request.meta.get("prior_failures", 0),
                    )
                    logger.warning(
                        "[RATE_LIMIT_SUSPECTED] %s delay: %.1f → %.1f",
                        domain,
                        current_delay,
                        new_delay,
                    )

        store = str(request.meta.get("store_name") or getattr(spider, "store_name", "") or spider.name)
        purpose = str(request.meta.get("access_purpose") or "listing")
        profile = get_store_profile(store)
        signal = detect_ban_signal(
            response,
            request=request,
            empty_body_threshold=profile.empty_body_threshold,
        )

        if signal is None:
            return response

        if signal == "mobile_redirect":
            # MobileRedirectMiddleware (later in chain) performs one desktop retry.
            return response

        access_metrics.bump("ban_signals_total")
        if signal == "captcha":
            access_metrics.bump("captcha_hits_total")
        if signal == "empty_shell":
            access_metrics.bump("empty_shell_hits_total")

        _access_json(
            "BAN_SIGNAL_DETECTED",
            spider=spider.name,
            store=store,
            purpose=purpose,
            url=response.url,
            detected_signal=signal,
            mode=request.meta.get("access_mode_selected"),
            retry_count=request.meta.get("prior_failures", 0),
        )

        mw_round = int(request.meta.get("access_mw_retry", 0))
        if mw_round >= 8:
            return response

        supports_pw = _spider_supports_playwright(spider)
        prior = int(request.meta.get("prior_failures", 0))

        strikes = int(request.meta.get("access_shell_strikes", 0))
        if signal in ("js_shell", "empty_shell"):
            strikes += 1

        shell_fail = strikes if signal in ("js_shell", "empty_shell") else prior + 1

        if should_escalate_to_browser(
            store,
            purpose,
            signal,
            shell_fail,
            spider_supports_browser=supports_pw,
        ):
            access_metrics.bump("browser_escalations_total")
            _access_json(
                "BROWSER_ESCALATION",
                spider=spider.name,
                store=store,
                purpose=purpose,
                url=request.url,
                detected_signal=signal,
                mode="browser",
                retry_count=prior + 1,
                reason=signal,
            )
            return self._retry_with_access(
                request,
                spider,
                purpose,
                store,
                prior_failures=prior + 1,
                force_browser=True,
                force_proxy=False,
                detected_signal=signal,
                shell_strikes=0,
                mw_round=mw_round + 1,
            )

        if should_escalate_to_proxy(store, purpose, signal, prior + 1):
            access_metrics.bump("proxy_escalations_total")
            _access_json(
                "PROXY_ESCALATION",
                spider=spider.name,
                store=store,
                purpose=purpose,
                url=request.url,
                detected_signal=signal,
                mode="proxy",
                retry_count=prior + 1,
                reason=signal,
            )
            return self._retry_with_access(
                request,
                spider,
                purpose,
                store,
                prior_failures=prior + 1,
                force_browser=False,
                force_proxy=True,
                detected_signal=signal,
                shell_strikes=strikes,
                mw_round=mw_round + 1,
            )

        # Accumulate shell samples before escalation threshold (same access tier).
        if signal in ("js_shell", "empty_shell") and strikes < app_settings.SCRAPY_ACCESS_SHELL_ESCALATE_AFTER:
            access_metrics.bump("retry_ban_total")
            _access_json(
                "REQUEST_RETRY_CLASSIFIED",
                spider=spider.name,
                store=store,
                purpose=purpose,
                url=request.url,
                detected_signal=signal,
                mode=request.meta.get("access_mode_selected"),
                retry_count=prior + 1,
                reason="shell_sample",
            )
            return self._retry_with_access(
                request,
                spider,
                purpose,
                store,
                prior_failures=prior,
                force_browser=False,
                force_proxy=False,
                detected_signal=signal,
                shell_strikes=strikes,
                mw_round=mw_round + 1,
            )

        return response

    def _retry_with_access(
        self,
        request: scrapy.http.Request,
        spider,
        purpose: str,
        store: str,
        *,
        prior_failures: int,
        force_browser: bool,
        force_proxy: bool,
        detected_signal: str | None,
        shell_strikes: int,
        mw_round: int,
    ) -> scrapy.http.Request:
        nr = request.copy()
        nr.dont_filter = True
        nr.meta["retry_times"] = nr.meta.get("retry_times", 0) + 1
        nr.meta["prior_failures"] = prior_failures
        nr.meta["force_browser"] = force_browser
        nr.meta["force_proxy"] = force_proxy
        nr.meta["access_last_signal"] = detected_signal
        nr.meta["access_shell_strikes"] = shell_strikes
        nr.meta["access_mw_retry"] = mw_round

        strat = build_request_meta(
            store,
            purpose,
            prior_failures=prior_failures,
            force_browser=force_browser,
            force_proxy=force_proxy,
            detected_signal=detected_signal,
            spider_supports_browser=_spider_supports_playwright(spider),
            record_mode_metrics=False,
        )
        nr.meta.update(strat)

        referer = nr.meta.get("from_listing") or nr.meta.get("access_referer")
        headers = build_desktop_headers(store, purpose, referer=referer)
        for k, v in headers.items():
            nr.headers[k] = v
        return nr


AdaptiveRateLimitMiddleware = AccessAwareRateLimitMiddleware
