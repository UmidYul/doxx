from __future__ import annotations

from unittest.mock import patch

import scrapy
from scrapy.http import TextResponse

from config.settings import settings as app_settings
from infrastructure.access.store_profiles import StoreAccessProfile
from infrastructure.spiders.honeypot_filter import filter_honeypot_links


def _response(url: str, body: str) -> TextResponse:
    req = scrapy.Request(url)
    return TextResponse(url=url, request=req, body=body.encode("utf-8"), encoding="utf-8")


def test_filter_disabled_returns_original(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", False)
    response = _response(
        "https://example.com/cat",
        '<html><body><a href="/p/1" style="display:none">x</a></body></html>',
    )
    urls = ["https://example.com/p/1"]

    kept, result = filter_honeypot_links(
        response,
        urls,
        store_name="mediapark",
        link_kind="product",
    )

    assert kept == urls
    assert result.dropped_count == 0
    assert result.reason == "disabled"


def test_filter_drops_hidden_links_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO", 0.9)
    response = _response(
        "https://example.com/cat",
        """
        <html><body>
          <a href="/p/hidden" style="display:none">trap</a>
          <a href="/p/visible">ok</a>
        </body></html>
        """,
    )
    urls = ["https://example.com/p/hidden", "https://example.com/p/visible"]

    with patch("infrastructure.spiders.honeypot_filter.is_feature_enabled", return_value=True):
        kept, result = filter_honeypot_links(
            response,
            urls,
            store_name="mediapark",
            link_kind="product",
        )

    assert kept == ["https://example.com/p/visible"]
    assert result.dropped_count == 1
    assert result.bypassed is False


def test_filter_bypasses_when_drop_ratio_too_high(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO", 0.3)
    response = _response(
        "https://example.com/cat",
        """
        <html><body>
          <div hidden><a href="/p/1">1</a></div>
          <div hidden><a href="/p/2">2</a></div>
          <div hidden><a href="/p/3">3</a></div>
        </body></html>
        """,
    )
    urls = [
        "https://example.com/p/1",
        "https://example.com/p/2",
        "https://example.com/p/3",
    ]

    with patch("infrastructure.spiders.honeypot_filter.is_feature_enabled", return_value=True):
        kept, result = filter_honeypot_links(
            response,
            urls,
            store_name="mediapark",
            link_kind="product",
        )

    assert kept == urls
    assert result.bypassed is True
    assert result.reason and result.reason.startswith("ratio_guard:")


def test_store_profile_custom_tokens_are_used(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", True)
    profile = StoreAccessProfile(
        store_name="teststore",
        mode="browser_fallback",
        honeypot_filter_enabled=True,
        honeypot_tokens=["trap-token"],
    )
    response = _response(
        "https://example.com/cat",
        '<html><body><a href="/p/t1" class="trap-token">x</a><a href="/p/t2">y</a></body></html>',
    )
    urls = ["https://example.com/p/t1", "https://example.com/p/t2"]

    with patch("infrastructure.spiders.honeypot_filter.get_store_profile", return_value=profile):
        kept, result = filter_honeypot_links(
            response,
            urls,
            store_name="teststore",
            link_kind="product",
        )

    assert kept == ["https://example.com/p/t2"]
    assert result.dropped_count == 1
