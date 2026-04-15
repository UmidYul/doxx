from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import scrapy
from scrapy.http import HtmlResponse
from scrapy.settings import Settings as ScrapySettings

from config.settings import settings as app_settings
from infrastructure.access.backoff_engine import BackoffDecision
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


def test_ratelimit_middleware_backoff_is_log_only(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", False)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", [])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)

    spider = _Spider()
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "access_purpose": "listing", "prior_failures": 1},
    )
    resp = HtmlResponse(
        url=req.url,
        request=req,
        status=429,
        headers={"Retry-After": "9"},
        body=b"<html>rate-limited</html>",
        encoding="utf-8",
    )
    mw = AccessAwareRateLimitMiddleware(_crawler())

    with (
        patch(
            "infrastructure.middlewares.ratelimit_middleware.is_feature_enabled",
            side_effect=lambda feature_name, *args, **kwargs: feature_name == "explicit_backoff_engine",
        ),
        patch("infrastructure.middlewares.ratelimit_middleware.detect_ban_signal", return_value=None),
    ):
        out = mw.process_response(req, resp, spider)

    assert out is resp
    assert req.meta["access_backoff_reason"] == "http_429_retry_after"
    assert req.meta["access_backoff_wait_seconds"] == 9.0
    assert spider.download_delay == 1.0


def test_retry_middleware_uses_backoff_reason_but_keeps_wait_formula(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", False)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", [])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)

    req = scrapy.Request(
        "https://example.com/p/1",
        meta={"store_name": "mediapark", "access_purpose": "product", "retry_times": 0},
    )
    resp = HtmlResponse(url=req.url, request=req, status=503, body=b"<html>upstream</html>", encoding="utf-8")
    spider = _Spider()
    mw = ExponentialRetryMiddleware(ScrapySettings({"RETRY_ENABLED": True}))
    mw._retry = lambda request, reason: request.copy()  # type: ignore[method-assign]

    with patch(
        "infrastructure.middlewares.retry_middleware.is_feature_enabled",
        side_effect=lambda feature_name, *args, **kwargs: feature_name == "explicit_backoff_engine",
    ):
        retried = mw.process_response(req, resp, spider)

    assert isinstance(retried, scrapy.Request)
    assert retried.meta["retry_reason"] == "http_503_upstream_error"
    assert retried.meta["download_timeout"] == 11


def test_ratelimit_middleware_backoff_enforcement_applies_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", [])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)

    spider = _Spider()
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "access_purpose": "listing", "prior_failures": 0},
    )
    resp = HtmlResponse(
        url=req.url,
        request=req,
        status=429,
        headers={"Retry-After": "9"},
        body=b"<html>rate-limited</html>",
        encoding="utf-8",
    )
    mw = AccessAwareRateLimitMiddleware(_crawler())

    with (
        patch(
            "infrastructure.middlewares.ratelimit_middleware.is_feature_enabled",
            side_effect=lambda feature_name, *args, **kwargs: feature_name
            in {"explicit_backoff_engine", "explicit_backoff_enforcement"},
        ),
        patch("infrastructure.middlewares.ratelimit_middleware.detect_ban_signal", return_value=None),
    ):
        out = mw.process_response(req, resp, spider)

    assert out is resp
    assert req.meta["access_backoff_reason"] == "http_429_retry_after"
    assert req.meta["access_backoff_cooldown_applied"] == 9.0
    assert spider.download_delay == 9.0


def test_ratelimit_backoff_enforcement_respects_store_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", ["texnomart"])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)

    spider = _Spider()
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "access_purpose": "listing", "prior_failures": 0},
    )
    resp = HtmlResponse(
        url=req.url,
        request=req,
        status=429,
        headers={"Retry-After": "9"},
        body=b"<html>rate-limited</html>",
        encoding="utf-8",
    )
    mw = AccessAwareRateLimitMiddleware(_crawler())

    with (
        patch(
            "infrastructure.middlewares.ratelimit_middleware.is_feature_enabled",
            side_effect=lambda feature_name, *args, **kwargs: feature_name
            in {"explicit_backoff_engine", "explicit_backoff_enforcement"},
        ),
        patch("infrastructure.middlewares.ratelimit_middleware.detect_ban_signal", return_value=None),
    ):
        out = mw.process_response(req, resp, spider)

    assert out is resp
    assert req.meta["access_backoff_reason"] == "http_429_retry_after"
    assert "access_backoff_cooldown_applied" not in req.meta
    assert spider.download_delay == 1.0


def test_retry_middleware_backoff_enforcement_uses_explicit_wait(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", [])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)

    req = scrapy.Request(
        "https://example.com/p/1",
        meta={"store_name": "mediapark", "access_purpose": "product", "retry_times": 0},
    )
    resp = HtmlResponse(
        url=req.url,
        request=req,
        status=429,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "15"},
        body=b"<html>upstream</html>",
        encoding="utf-8",
    )
    spider = _Spider()
    mw = ExponentialRetryMiddleware(ScrapySettings({"RETRY_ENABLED": True}))
    mw._retry = lambda request, reason: request.copy()  # type: ignore[method-assign]

    with patch(
        "infrastructure.middlewares.retry_middleware.is_feature_enabled",
        side_effect=lambda feature_name, *args, **kwargs: feature_name
        in {"explicit_backoff_engine", "explicit_backoff_enforcement"},
    ):
        retried = mw.process_response(req, resp, spider)

    assert isinstance(retried, scrapy.Request)
    assert retried.meta["retry_reason"] == "http_429_ratelimit_reset"
    assert retried.meta["download_timeout"] == 25
    assert retried.meta["access_backoff_wait_applied"] == 15


def test_retry_middleware_backoff_enforcement_can_block_retry(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE", True)
    monkeypatch.setattr(app_settings, "SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES", [])
    monkeypatch.setattr(app_settings, "SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED", False)
    monkeypatch.setattr(app_settings, "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED", False)

    req = scrapy.Request(
        "https://example.com/p/1",
        meta={"store_name": "mediapark", "access_purpose": "product", "retry_times": 0},
    )
    resp = HtmlResponse(url=req.url, request=req, status=503, body=b"<html>upstream</html>", encoding="utf-8")
    spider = _Spider()
    mw = ExponentialRetryMiddleware(ScrapySettings({"RETRY_ENABLED": True}))
    mw._retry = lambda request, reason: request.copy()  # type: ignore[method-assign]

    with (
        patch(
            "infrastructure.middlewares.retry_middleware.is_feature_enabled",
            side_effect=lambda feature_name, *args, **kwargs: feature_name
            in {"explicit_backoff_engine", "explicit_backoff_enforcement"},
        ),
        patch.object(
            mw._backoff_engine,
            "classify",
            return_value=BackoffDecision(
                status=503,
                reason="test_block",
                retry_allowed=False,
                wait_seconds=0.0,
                cooldown_seconds=0.0,
                actions=(),
            ),
        ),
    ):
        out = mw.process_response(req, resp, spider)

    assert out is resp
    assert req.meta["access_backoff_retry_blocked"] is True
