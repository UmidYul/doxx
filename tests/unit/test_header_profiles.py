from __future__ import annotations

from unittest.mock import patch

import pytest

from config.settings import settings as app_settings
from infrastructure.access import header_profiles as hp
from infrastructure.access.store_profiles import StoreAccessProfile


def test_legacy_fallback_when_rotation_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HEADER_PROFILE_ROTATION_ENABLED", False)
    hp._reset_rotation_state_for_tests()

    headers = hp.build_desktop_headers(
        "mediapark",
        "product",
        request_url="https://mediapark.uz/products/view/demo-1",
    )

    assert "Chrome/122.0.0.0" in headers["User-Agent"]
    assert headers["Accept-Language"] == "ru-RU,ru;q=0.9,uz-UZ,uz;q=0.8,en;q=0.7"
    assert headers["Sec-Fetch-Mode"] == "navigate"
    assert headers.get("Sec-Fetch-User") is None


def test_rotation_enabled_round_robin_changes_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HEADER_PROFILE_ROTATION_ENABLED", True)
    hp._reset_rotation_state_for_tests()

    with patch("infrastructure.access.header_profiles.is_feature_enabled", return_value=True):
        h1 = hp.build_desktop_headers(
            "mediapark",
            "listing",
            request_url="https://mediapark.uz/products/category/phones",
        )
        h2 = hp.build_desktop_headers(
            "mediapark",
            "listing",
            request_url="https://mediapark.uz/products/category/phones",
        )

    assert h1["User-Agent"] != h2["User-Agent"]
    assert h1["Sec-Fetch-Dest"] == "document"
    assert h1["Sec-Fetch-Mode"] == "navigate"
    assert h1["Sec-Fetch-User"] == "?1"
    assert h1["Sec-Fetch-Site"] == "none"


def test_store_override_profile_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HEADER_PROFILE_ROTATION_ENABLED", True)
    hp._reset_rotation_state_for_tests()
    profile = StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        header_rotation_enabled=True,
        header_profile_ids=["firefox_win124_ru"],
    )

    with (
        patch("infrastructure.access.header_profiles.is_feature_enabled", return_value=True),
        patch("infrastructure.access.header_profiles.get_store_profile", return_value=profile),
    ):
        h1 = hp.build_desktop_headers(
            "mediapark",
            "listing",
            request_url="https://mediapark.uz/products/category/phones",
        )
        h2 = hp.build_desktop_headers(
            "mediapark",
            "listing",
            request_url="https://mediapark.uz/products/category/phones",
        )

    assert "Firefox/124.0" in h1["User-Agent"]
    assert "Firefox/124.0" in h2["User-Agent"]


def test_referer_policy_origin_on_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_HEADER_PROFILE_ROTATION_ENABLED", True)
    hp._reset_rotation_state_for_tests()
    profile = StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        header_rotation_enabled=True,
        header_profile_ids=["edge_win122_ru"],
    )

    with (
        patch("infrastructure.access.header_profiles.is_feature_enabled", return_value=True),
        patch("infrastructure.access.header_profiles.get_store_profile", return_value=profile),
    ):
        headers_auto = hp.build_desktop_headers(
            "mediapark",
            "product",
            request_url="https://mediapark.uz/products/view/demo-1",
        )
        headers_passthrough = hp.build_desktop_headers(
            "mediapark",
            "product",
            referer="https://mediapark.uz/products/category/phones",
            request_url="https://mediapark.uz/products/view/demo-1",
        )

    assert headers_auto["Referer"] == "https://mediapark.uz"
    assert headers_passthrough["Referer"] == "https://mediapark.uz/products/category/phones"
