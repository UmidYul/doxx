from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import scrapy
from scrapy.settings import Settings as ScrapySettings

from config.settings import settings as app_settings
from infrastructure.access.store_profiles import StoreAccessProfile
from infrastructure.middlewares.ratelimit_middleware import AccessAwareRateLimitMiddleware


class _FixedRng:
    """Deterministic RNG stub for jitter tests."""

    def __init__(self, magnitude: float, *, positive: bool = True) -> None:
        self._magnitude = magnitude
        self._positive = positive

    def uniform(self, a: float, b: float) -> float:
        _ = a, b
        return self._magnitude

    def random(self) -> float:
        return 0.9 if self._positive else 0.1


class _Spider:
    name = "mediapark"
    store_name = "mediapark"

    def __init__(self, delay: float = 1.5) -> None:
        self.settings = ScrapySettings({"DOWNLOAD_DELAY": delay})
        self.download_delay = delay


def _build_crawler(slot_key: str, *, initial_delay: float) -> tuple[SimpleNamespace, SimpleNamespace]:
    slot = SimpleNamespace(delay=initial_delay)
    downloader = SimpleNamespace(slots={slot_key: slot})
    crawler = SimpleNamespace(engine=SimpleNamespace(downloader=downloader))
    return crawler, slot


def test_jitter_disabled_keeps_slot_delay_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)

    crawler, slot = _build_crawler("example.com", initial_delay=1.5)
    mw = AccessAwareRateLimitMiddleware(crawler, rng=_FixedRng(0.2, positive=True))
    spider = _Spider(delay=1.5)
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "download_slot": "example.com"},
    )

    mw.process_request(req, spider)

    assert slot.delay == pytest.approx(1.5)
    assert "access_jitter_delta" not in req.meta


def test_jitter_uses_domain_base_delay_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_MIN_SECONDS", 0.05)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_MAX_SECONDS", 0.25)

    crawler, slot = _build_crawler("example.com", initial_delay=0.0)
    mw = AccessAwareRateLimitMiddleware(crawler, rng=_FixedRng(0.2, positive=True))
    mw.download_delays["example.com"] = 2.0
    spider = _Spider(delay=1.0)
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "download_slot": "example.com"},
    )

    with patch("infrastructure.middlewares.ratelimit_middleware.is_feature_enabled", return_value=True):
        mw.process_request(req, spider)

    assert slot.delay == pytest.approx(2.2)
    assert req.meta["access_jitter_delta"] == pytest.approx(0.2)


def test_store_profile_override_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_MIN_SECONDS", 0.05)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_MAX_SECONDS", 0.25)

    profile = StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        jitter_enabled=True,
        jitter_min_seconds=0.4,
        jitter_max_seconds=0.6,
    )

    crawler, slot = _build_crawler("example.com", initial_delay=0.0)
    mw = AccessAwareRateLimitMiddleware(crawler, rng=_FixedRng(0.5, positive=True))
    mw.download_delays["example.com"] = 1.0
    spider = _Spider(delay=1.0)
    req = scrapy.Request(
        "https://example.com/catalog",
        meta={"store_name": "mediapark", "download_slot": "example.com"},
    )

    with (
        patch("infrastructure.middlewares.ratelimit_middleware.is_feature_enabled", return_value=True),
        patch("infrastructure.middlewares.ratelimit_middleware.get_store_profile", return_value=profile),
    ):
        mw.process_request(req, spider)

    assert slot.delay == pytest.approx(1.5)
