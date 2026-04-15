from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import scrapy
from scrapy.http import HtmlResponse
from scrapy.settings import Settings as ScrapySettings

from config.settings import settings as app_settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.ban_signal_monitoring import (
    ban_signal_spike_monitor,
    status_bucket_for_http,
)
from infrastructure.middlewares.ratelimit_middleware import AccessAwareRateLimitMiddleware
from infrastructure.middlewares.retry_middleware import ExponentialRetryMiddleware


class _Spider:
    name = "mediapark"
    store_name = "mediapark"

    def __init__(self) -> None:
        self.settings = ScrapySettings({"DOWNLOAD_DELAY": 1.0, "DOWNLOAD_HANDLERS": {}})
        self.download_delay = 1.0


def _crawler() -> SimpleNamespace:
    return SimpleNamespace(engine=SimpleNamespace(downloader=SimpleNamespace(slots={})))


def test_status_bucket_for_http_values() -> None:
    assert status_bucket_for_http(403) == "403"
    assert status_bucket_for_http(429) == "429"
    assert status_bucket_for_http(503) == "5xx"
    assert status_bucket_for_http(200) is None


def test_spike_monitor_triggers_once_per_burst_and_rearms() -> None:
    ban_signal_spike_monitor.reset()
    fired, count = ban_signal_spike_monitor.record_http_status(
        store="mediapark",
        domain="example.com",
        status_bucket="403",
        threshold=2,
        window_seconds=10.0,
        now_monotonic=1.0,
    )
    assert fired is False
    assert count == 1

    fired, count = ban_signal_spike_monitor.record_http_status(
        store="mediapark",
        domain="example.com",
        status_bucket="403",
        threshold=2,
        window_seconds=10.0,
        now_monotonic=2.0,
    )
    assert fired is True
    assert count == 2

    fired, count = ban_signal_spike_monitor.record_http_status(
        store="mediapark",
        domain="example.com",
        status_bucket="403",
        threshold=2,
        window_seconds=10.0,
        now_monotonic=3.0,
    )
    assert fired is False
    assert count == 3

    fired, count = ban_signal_spike_monitor.record_http_status(
        store="mediapark",
        domain="example.com",
        status_bucket="403",
        threshold=2,
        window_seconds=10.0,
        now_monotonic=30.0,
    )
    assert fired is False
    assert count == 1

    fired, count = ban_signal_spike_monitor.record_http_status(
        store="mediapark",
        domain="example.com",
        status_bucket="403",
        threshold=2,
        window_seconds=10.0,
        now_monotonic=31.0,
    )
    assert fired is True
    assert count == 2


def test_ratelimit_monitoring_records_status_and_spike(monkeypatch) -> None:
    access_metrics.reset()
    ban_signal_spike_monitor.reset()
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SPIKE_THRESHOLD", 2)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SPIKE_WINDOW_SECONDS", 120.0)
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)

    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "access_purpose": "listing", "prior_failures": 0},
    )
    resp1 = HtmlResponse(url=req.url, request=req, status=403, body=b"<html>blocked</html>", encoding="utf-8")
    resp2 = HtmlResponse(url=req.url, request=req, status=403, body=b"<html>blocked</html>", encoding="utf-8")
    spider = _Spider()
    mw = AccessAwareRateLimitMiddleware(_crawler())

    with (
        patch("infrastructure.middlewares.ratelimit_middleware.is_feature_enabled", return_value=True),
        patch("infrastructure.middlewares.ratelimit_middleware.detect_ban_signal", return_value=None),
    ):
        out1 = mw.process_response(req, resp1, spider)
        out2 = mw.process_response(req, resp2, spider)

    assert out1 is resp1
    assert out2 is resp2
    data = access_metrics.to_dict()
    assert data["http_403_total"] == 2
    assert data["http_status_spikes_total"] == 1
    labeled = access_metrics.labeled_snapshot()
    assert any(
        key.startswith("http_status_total|store=mediapark|domain=example.com|status=403")
        for key in labeled
    )


def test_retry_middleware_records_reason_breakdown(monkeypatch) -> None:
    access_metrics.reset()
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", True)
    req = scrapy.Request(
        "https://example.com/p/1",
        meta={
            "store_name": "mediapark",
            "access_purpose": "product",
            "retry_reason": "shell_sample",
            "retry_times": 0,
        },
    )
    resp = HtmlResponse(url=req.url, request=req, status=429, body=b"<html>retry</html>", encoding="utf-8")
    spider = _Spider()
    mw = ExponentialRetryMiddleware(ScrapySettings({"RETRY_ENABLED": True}))
    mw._retry = lambda request, reason: request.copy()  # type: ignore[method-assign]

    with patch("infrastructure.middlewares.retry_middleware.is_feature_enabled", return_value=True):
        retried = mw.process_response(req, resp, spider)

    assert isinstance(retried, scrapy.Request)
    data = access_metrics.to_dict()
    assert data["retry_http_total"] == 1
    assert data["retries_by_reason_total"] == 1
    labeled = access_metrics.labeled_snapshot()
    assert any(
        key.startswith(
            "retries_by_reason_total|store=mediapark|domain=example.com|reason=shell_sample|status=429"
        )
        for key in labeled
    )
