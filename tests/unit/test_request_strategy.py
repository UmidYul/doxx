from __future__ import annotations

from unittest.mock import patch

import pytest

from config.settings import settings
from infrastructure.access.store_profiles import StoreAccessProfile
from infrastructure.access.request_strategy import (
    build_request_meta,
    should_escalate_to_proxy,
    should_escalate_to_browser,
    should_use_proxy,
    should_use_browser,
)


def test_http_only_profile_no_browser_without_signal():
    with patch("infrastructure.access.request_strategy.get_store_profile") as gp:
        gp.return_value = StoreAccessProfile(
            store_name="x",
            mode="http_only",
            supports_browser=True,
            fallback_to_browser=False,
            fallback_to_proxy=False,
            empty_body_threshold=256,
        )
        assert (
            should_use_browser(
                "x",
                "listing",
                prior_failures=0,
                force_browser=False,
                spider_supports_browser=True,
            )
            is False
        )


def test_browser_required_builds_meta_when_spider_supports_pw():
    with patch("infrastructure.access.request_strategy.get_store_profile") as gp:
        gp.return_value = StoreAccessProfile(
            store_name="x",
            mode="browser_required",
            supports_browser=True,
            fallback_to_browser=True,
        )
        meta = build_request_meta(
            "x",
            "listing",
            spider_supports_browser=True,
        )
    assert meta.get("playwright") is True
    assert meta.get("access_mode_selected") == "browser"


def test_mediapark_first_hop_plain_http():
    meta = build_request_meta(
        "mediapark",
        "listing",
        spider_supports_browser=False,
    )
    assert meta.get("access_mode_selected") == "plain"
    assert meta.get("playwright") is None


def test_repeated_empty_shell_escalation_decision():
    with patch.object(settings, "SCRAPY_ACCESS_SHELL_ESCALATE_AFTER", 2):
        assert (
            should_escalate_to_browser(
                "mediapark",
                "listing",
                "empty_shell",
                2,
                spider_supports_browser=True,
            )
            is True
        )


def test_cloudflare_challenge_escalates_on_first_failure_count():
    assert (
        should_escalate_to_browser(
            "mediapark",
            "listing",
            "cloudflare_challenge",
            1,
            spider_supports_browser=True,
        )
        is True
    )


def test_deterministic_same_inputs_same_meta_keys():
    a = build_request_meta("mediapark", "product", prior_failures=0, spider_supports_browser=False)
    b = build_request_meta("mediapark", "product", prior_failures=0, spider_supports_browser=False)
    assert a["access_mode_selected"] == b["access_mode_selected"]
    assert set(a.keys()) == set(b.keys())


def test_proxy_disabled_profile_blocks_proxy_usage_even_when_forced():
    with patch("infrastructure.access.request_strategy.get_store_profile") as gp:
        gp.return_value = StoreAccessProfile(
            store_name="x",
            mode="http_with_proxy",
            proxy_enabled=False,
            fallback_to_proxy=True,
        )
        assert should_use_proxy("x", "listing", force_proxy=True) is False
        assert should_escalate_to_proxy("x", "listing", "captcha", 3) is False
