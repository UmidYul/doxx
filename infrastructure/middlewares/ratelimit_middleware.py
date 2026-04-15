from __future__ import annotations

import json
import logging
from random import Random
import time
from collections import deque
from statistics import median
from urllib.parse import urlparse

import scrapy.http

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import settings as app_settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.backoff_engine import (
    BackoffDecision,
    ExplicitBackoffEngine,
    RateLimitHeaderSnapshot,
)
from infrastructure.access.ban_signal_monitoring import (
    ban_signal_spike_monitor,
    status_bucket_for_http,
)
from infrastructure.access.ban_detector import detect_ban_signal
from infrastructure.access.captcha_hooks import (
    CaptchaDetectionResult,
    CaptchaSignalDetector,
    CaptchaSolver,
    build_captcha_solver,
)
from infrastructure.access.header_profiles import build_desktop_headers
from infrastructure.access.proxy_policy import mark_proxy_result
from infrastructure.access.request_strategy import (
    build_request_meta,
    should_escalate_to_browser,
    should_escalate_to_proxy,
)
from infrastructure.access.store_profiles import StoreAccessProfile, get_store_profile

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

    def __init__(
        self,
        crawler=None,
        *,
        rng: Random | None = None,
        captcha_detector: CaptchaSignalDetector | None = None,
        captcha_solver: CaptchaSolver | None = None,
    ) -> None:
        self.response_times: dict[str, deque[float]] = {}
        self.download_delays: dict[str, float] = {}
        self._crawler = crawler
        self._rng = rng or Random()
        self._captcha_detector = captcha_detector or CaptchaSignalDetector(
            suspicious_redirect_enabled=bool(
                getattr(app_settings, "SCRAPY_CAPTCHA_SUSPICIOUS_REDIRECT_ENABLED", True)
            )
        )
        self._captcha_solver = captcha_solver or build_captcha_solver(app_settings)
        self._backoff_engine = ExplicitBackoffEngine.from_settings(app_settings)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request: scrapy.http.Request, spider):
        request.meta.setdefault("_request_start", time.monotonic())
        self._apply_randomized_delay(request, spider)

    @staticmethod
    def _extract_domain(url: str) -> str:
        return (urlparse(url).netloc or "").strip().lower()

    @staticmethod
    def _store_name(request: scrapy.http.Request, spider) -> str:
        return str(request.meta.get("store_name") or getattr(spider, "store_name", "") or spider.name)

    @staticmethod
    def _resolve_jitter_bounds(profile: StoreAccessProfile) -> tuple[float, float]:
        low = profile.jitter_min_seconds
        high = profile.jitter_max_seconds
        if low is None:
            low = app_settings.SCRAPY_RANDOMIZED_DELAY_MIN_SECONDS
        if high is None:
            high = app_settings.SCRAPY_RANDOMIZED_DELAY_MAX_SECONDS
        low_f = max(0.0, float(low))
        high_f = max(0.0, float(high))
        if low_f > high_f:
            low_f, high_f = high_f, low_f
        return low_f, high_f

    def _is_jitter_enabled(self, store: str) -> bool:
        if not app_settings.SCRAPY_RANDOMIZED_DELAY_ENABLED:
            return False
        return is_feature_enabled("access_delay_jitter", store)

    @staticmethod
    def _is_ban_monitoring_enabled(store: str) -> bool:
        if not getattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False):
            return False
        return is_feature_enabled("ban_signal_monitoring", store)

    @staticmethod
    def _is_captcha_hooks_enabled(store: str) -> bool:
        if not getattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", False):
            return False
        return is_feature_enabled("captcha_hooks", store)

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

    def _get_downloader_slot(self, slot_key: str):
        engine = getattr(self._crawler, "engine", None)
        downloader = getattr(engine, "downloader", None)
        slots = getattr(downloader, "slots", None)
        if isinstance(slots, dict):
            return slots.get(slot_key)
        return None

    def _apply_slot_delay(self, request: scrapy.http.Request, spider, domain: str, delay: float) -> None:
        slot_key = str(request.meta.get("download_slot") or domain)
        slot = self._get_downloader_slot(slot_key)
        if slot is not None and hasattr(slot, "delay"):
            slot.delay = delay
            return
        spider.download_delay = delay

    def _apply_randomized_delay(self, request: scrapy.http.Request, spider) -> None:
        store = self._store_name(request, spider)
        if not self._is_jitter_enabled(store):
            return
        profile = get_store_profile(store)
        if profile.jitter_enabled is False:
            return
        domain = self._extract_domain(request.url)
        if not domain:
            return
        jitter_min, jitter_max = self._resolve_jitter_bounds(profile)
        if jitter_max <= 0.0:
            return
        base_delay = self.download_delays.get(domain, spider.settings.getfloat("DOWNLOAD_DELAY", 1.0))
        base_delay = max(0.0, float(base_delay))
        magnitude = self._rng.uniform(jitter_min, jitter_max)
        signed_delta = magnitude if self._rng.random() >= 0.5 else -magnitude
        effective_delay = max(0.0, base_delay + signed_delta)
        self._apply_slot_delay(request, spider, domain, effective_delay)
        request.meta["access_effective_delay"] = round(effective_delay, 4)
        request.meta["access_jitter_delta"] = round(signed_delta, 4)
        access_metrics.bump("request_jitter_applied_total")

    def _record_status_monitoring(
        self,
        *,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
        store: str,
        domain: str,
        purpose: str,
    ) -> None:
        if not self._is_ban_monitoring_enabled(store):
            return
        bucket = status_bucket_for_http(int(response.status))
        if bucket is None:
            return

        if bucket == "403":
            access_metrics.bump("http_403_total")
        elif bucket == "429":
            access_metrics.bump("http_429_total")
        else:
            access_metrics.bump("http_5xx_total")
        access_metrics.bump_labeled("http_status_total", store=store, domain=domain, status=bucket)

        triggered, count = ban_signal_spike_monitor.record_http_status(
            store=store,
            domain=domain,
            status_bucket=bucket,
            threshold=int(getattr(app_settings, "SCRAPY_BAN_SPIKE_THRESHOLD", 5)),
            window_seconds=float(getattr(app_settings, "SCRAPY_BAN_SPIKE_WINDOW_SECONDS", 120.0)),
        )
        if not triggered:
            return
        access_metrics.bump("http_status_spikes_total")
        access_metrics.bump_labeled(
            "http_status_spikes_total",
            store=store,
            domain=domain,
            status=bucket,
        )
        _access_json(
            "BAN_STATUS_SPIKE",
            spider=spider.name,
            store=store,
            purpose=purpose,
            url=request.url,
            status_bucket=bucket,
            status_count_window=count,
            window_seconds=getattr(app_settings, "SCRAPY_BAN_SPIKE_WINDOW_SECONDS", 120.0),
            threshold=getattr(app_settings, "SCRAPY_BAN_SPIKE_THRESHOLD", 5),
        )

    def _record_explicit_backoff_decision(
        self,
        *,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
        store: str,
        domain: str,
        purpose: str,
    ) -> BackoffDecision | None:
        if not self._is_explicit_backoff_enabled(store):
            return None
        status = int(response.status)
        if not self._backoff_engine.supports_status(status):
            return None

        header_snapshot = RateLimitHeaderSnapshot()
        if bool(getattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)):
            header_snapshot = self._backoff_engine.parse_headers(response.headers)
            if header_snapshot.has_hints:
                access_metrics.bump("explicit_backoff_header_hints_total")

        decision = self._backoff_engine.classify(
            status=status,
            prior_failures=int(request.meta.get("prior_failures", 0)),
            headers_snapshot=header_snapshot,
        )
        request.meta["access_backoff_reason"] = decision.reason
        request.meta["access_backoff_wait_seconds"] = round(float(decision.wait_seconds), 3)
        request.meta["access_backoff_cooldown_seconds"] = round(float(decision.cooldown_seconds), 3)
        if decision.actions:
            request.meta["access_backoff_actions"] = list(decision.actions)

        access_metrics.bump("explicit_backoff_decisions_total")
        if decision.retry_allowed:
            access_metrics.bump("explicit_backoff_retry_suggested_total")
        if decision.cooldown_seconds > 0:
            access_metrics.bump("explicit_backoff_cooldown_suggested_total")
        if self._is_ban_monitoring_enabled(store):
            access_metrics.bump_labeled(
                "explicit_backoff_decisions_total",
                store=store,
                domain=domain,
                reason=decision.reason,
                status=status,
            )

        _access_json(
            "EXPLICIT_BACKOFF_DECIDED",
            spider=spider.name,
            store=store,
            purpose=purpose,
            url=request.url,
            status=status,
            reason=decision.reason,
            retry_allowed=decision.retry_allowed,
            wait_seconds=round(decision.wait_seconds, 3),
            cooldown_seconds=round(decision.cooldown_seconds, 3),
            actions=list(decision.actions),
            has_rate_limit_hints=header_snapshot.has_hints,
        )
        return decision

    @staticmethod
    def _bump_retry_reason_metric(store: str, domain: str, reason: str, *, status: int | None = None) -> None:
        if not getattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False):
            return
        if not is_feature_enabled("ban_signal_monitoring", store):
            return
        access_metrics.bump("retries_by_reason_total")
        access_metrics.bump_labeled(
            "retries_by_reason_total",
            store=store,
            domain=domain,
            reason=reason,
            status=status,
        )

    def _run_captcha_solver(
        self,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
        *,
        detection: CaptchaDetectionResult,
        store: str,
        purpose: str,
    ) -> scrapy.http.Request | None:
        if not detection.is_captcha_related():
            return None
        max_attempts = int(getattr(app_settings, "SCRAPY_CAPTCHA_MAX_SOLVE_ATTEMPTS", 1))
        attempts = int(request.meta.get("captcha_solver_attempts", 0))
        if attempts >= max_attempts:
            return None

        access_metrics.bump("captcha_solver_attempt_total")
        result = self._captcha_solver.solve(
            request,
            response,
            spider,
            detection=detection,
            store=store,
            purpose=purpose,
        )
        if result.solver == "noop":
            access_metrics.bump("captcha_solver_noop_total")
        if result.handled:
            access_metrics.bump("captcha_solver_handled_total")

        _access_json(
            "CAPTCHA_SOLVER_RESULT",
            spider=spider.name,
            store=store,
            purpose=purpose,
            url=request.url,
            detected_signal=detection.signal,
            solver=result.solver,
            handled=result.handled,
            reason=result.reason,
            retry_count=request.meta.get("prior_failures", 0),
        )

        retry_request = result.retry_request
        if retry_request is None:
            return None
        retry_request.dont_filter = True
        retry_request.meta["captcha_solver_attempts"] = attempts + 1
        retry_request.meta["captcha_solver_name"] = result.solver
        if result.token:
            retry_request.meta["captcha_solver_token"] = result.token
        for k, v in (result.extra_meta or {}).items():
            retry_request.meta[k] = v
        return retry_request

    def process_response(
        self,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
    ):
        domain = self._extract_domain(request.url)
        store = str(request.meta.get("store_name") or getattr(spider, "store_name", "") or spider.name)
        purpose = str(request.meta.get("access_purpose") or "listing")

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
                    self._apply_slot_delay(request, spider, domain, new_delay)
                    access_metrics.bump("retry_transport_total")
                    _access_json(
                        "REQUEST_RETRY_CLASSIFIED",
                        spider=spider.name,
                        store=store,
                        purpose=purpose,
                        url=request.url,
                        reason="slow_origin_backoff",
                        mode="plain",
                        retry_count=request.meta.get("prior_failures", 0),
                    )
                    self._bump_retry_reason_metric(
                        store,
                        domain,
                        "slow_origin_backoff",
                        status=int(response.status),
                    )
                    logger.warning(
                        "[RATE_LIMIT_SUSPECTED] %s delay: %.1f → %.1f",
                        domain,
                        current_delay,
                        new_delay,
                    )

        self._record_status_monitoring(
            request=request,
            response=response,
            spider=spider,
            store=store,
            domain=domain,
            purpose=purpose,
        )
        backoff_decision = self._record_explicit_backoff_decision(
            request=request,
            response=response,
            spider=spider,
            store=store,
            domain=domain,
            purpose=purpose,
        )
        if (
            backoff_decision is not None
            and self._is_explicit_backoff_enforce_enabled(store)
            and backoff_decision.cooldown_seconds > 0.0
            and domain
        ):
            current_delay = self.download_delays.get(domain, spider.settings.getfloat("DOWNLOAD_DELAY", 1.0))
            new_delay = max(float(current_delay), float(backoff_decision.cooldown_seconds))
            self.download_delays[domain] = new_delay
            self._apply_slot_delay(request, spider, domain, new_delay)
            access_metrics.bump("explicit_backoff_cooldown_applied_total")
            request.meta["access_backoff_cooldown_applied"] = round(new_delay, 3)
            _access_json(
                "EXPLICIT_BACKOFF_COOLDOWN_APPLIED",
                spider=spider.name,
                store=store,
                purpose=purpose,
                url=request.url,
                domain=domain,
                reason=backoff_decision.reason,
                cooldown_seconds=round(backoff_decision.cooldown_seconds, 3),
                applied_delay=round(new_delay, 3),
            )
        proxy_url = str(request.meta.get("proxy") or "").strip() or None
        profile = get_store_profile(store)
        captcha_detection: CaptchaDetectionResult | None = None
        if self._is_captcha_hooks_enabled(store):
            captcha_detection = self._captcha_detector.detect(
                response,
                request=request,
                empty_body_threshold=profile.empty_body_threshold,
            )
            signal = captcha_detection.signal
            if captcha_detection.is_captcha_related():
                access_metrics.bump("captcha_hook_detected_total")
                request.meta["captcha_detection_markers"] = list(captcha_detection.markers)
                request.meta["captcha_suspicious_redirect"] = bool(captcha_detection.suspicious_redirect)
        else:
            signal = detect_ban_signal(
                response,
                request=request,
                empty_body_threshold=profile.empty_body_threshold,
            )

        if signal is None:
            if proxy_url:
                mark_proxy_result(proxy_url, success=True, reason="ok", store_name=store)
            return response

        if signal == "mobile_redirect":
            # MobileRedirectMiddleware (later in chain) performs one desktop retry.
            if proxy_url:
                mark_proxy_result(proxy_url, success=True, reason="mobile_redirect", store_name=store)
            return response

        if proxy_url:
            mark_proxy_result(proxy_url, success=False, reason=signal, store_name=store)
            if self._is_ban_monitoring_enabled(store):
                access_metrics.bump("proxy_bans_total")
                access_metrics.bump_labeled(
                    "proxy_bans_total",
                    store=store,
                    domain=domain,
                    reason=signal,
                )

        access_metrics.bump("ban_signals_total")
        if self._is_ban_monitoring_enabled(store):
            access_metrics.bump_labeled("ban_signals_total", store=store, domain=domain, reason=signal)
        if signal == "captcha":
            access_metrics.bump("captcha_hits_total")
            if self._is_ban_monitoring_enabled(store):
                access_metrics.bump_labeled("captcha_hits_total", store=store, domain=domain, reason=signal)
        if signal == "empty_shell":
            access_metrics.bump("empty_shell_hits_total")
            access_metrics.bump("empty_body_anomalies_total")
            if self._is_ban_monitoring_enabled(store):
                access_metrics.bump_labeled(
                    "empty_body_anomalies_total",
                    store=store,
                    domain=domain,
                    reason=signal,
                )

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

        if captcha_detection is not None and captcha_detection.is_captcha_related():
            solver_retry = self._run_captcha_solver(
                request,
                response,
                spider,
                detection=captcha_detection,
                store=store,
                purpose=purpose,
            )
            if solver_retry is not None:
                return solver_retry

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
            if self._is_ban_monitoring_enabled(store):
                access_metrics.bump_labeled(
                    "browser_escalations_total",
                    store=store,
                    domain=domain,
                    reason=signal,
                )
            self._bump_retry_reason_metric(
                store,
                domain,
                "browser_escalation",
                status=int(response.status),
            )
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
                retry_reason="browser_escalation",
            )

        if should_escalate_to_proxy(store, purpose, signal, prior + 1):
            access_metrics.bump("proxy_escalations_total")
            if self._is_ban_monitoring_enabled(store):
                access_metrics.bump_labeled(
                    "proxy_escalations_total",
                    store=store,
                    domain=domain,
                    reason=signal,
                )
            self._bump_retry_reason_metric(
                store,
                domain,
                "proxy_escalation",
                status=int(response.status),
            )
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
                retry_reason="proxy_escalation",
            )

        # Accumulate shell samples before escalation threshold (same access tier).
        if signal in ("js_shell", "empty_shell") and strikes < app_settings.SCRAPY_ACCESS_SHELL_ESCALATE_AFTER:
            access_metrics.bump("retry_ban_total")
            self._bump_retry_reason_metric(
                store,
                domain,
                "shell_sample",
                status=int(response.status),
            )
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
                retry_reason="shell_sample",
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
        retry_reason: str | None = None,
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
        if retry_reason:
            nr.meta["retry_reason"] = retry_reason

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
        headers = build_desktop_headers(store, purpose, referer=referer, request_url=nr.url)
        for k, v in headers.items():
            nr.headers[k] = v
        return nr


AdaptiveRateLimitMiddleware = AccessAwareRateLimitMiddleware
