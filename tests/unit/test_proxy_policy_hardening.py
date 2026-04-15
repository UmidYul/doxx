from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from infrastructure.access import proxy_policy
from infrastructure.access.store_profiles import StoreAccessProfile


def _write_pool(path: Path, *entries: str) -> None:
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")


def test_legacy_mode_uses_first_proxy_when_hardening_disabled(tmp_path: Path) -> None:
    pool = tmp_path / "proxies.txt"
    _write_pool(pool, "http://8.8.8.8:8000", "http://9.9.9.9:9000")
    settings = Settings(
        PROXY_LIST_PATH=str(pool),
        SCRAPY_PROXY_POLICY_HARDENING_ENABLED=False,
        _env_file=None,
    )
    proxy_policy._reset_proxy_policy_state_for_tests()

    meta = proxy_policy.build_proxy_meta(
        "mediapark",
        "listing",
        settings=settings,
        target_url="https://mediapark.uz/products/category/phones",
    )

    assert meta.get("proxy") == "http://8.8.8.8:8000"
    assert meta.get("access_proxy_mode") == "legacy"


def test_rotating_mode_changes_proxy_across_requests(tmp_path: Path) -> None:
    pool = tmp_path / "proxies.txt"
    _write_pool(pool, "http://8.8.8.8:8000", "http://9.9.9.9:9000")
    settings = Settings(
        PROXY_LIST_PATH=str(pool),
        SCRAPY_PROXY_POLICY_HARDENING_ENABLED=True,
        SCRAPY_PROXY_POLICY_DEFAULT_MODE="rotating",
        _env_file=None,
    )
    proxy_policy._reset_proxy_policy_state_for_tests()

    with patch("infrastructure.access.proxy_policy.is_feature_enabled", return_value=True):
        m1 = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones",
        )
        m2 = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones",
        )

    assert m1.get("proxy") != m2.get("proxy")
    assert m1.get("access_proxy_mode") == "rotating"


def test_sticky_mode_keeps_proxy_for_same_store_domain(tmp_path: Path) -> None:
    pool = tmp_path / "proxies.txt"
    _write_pool(pool, "http://8.8.8.8:8000", "http://9.9.9.9:9000")
    settings = Settings(
        PROXY_LIST_PATH=str(pool),
        SCRAPY_PROXY_POLICY_HARDENING_ENABLED=True,
        _env_file=None,
    )
    profile = StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        proxy_mode="sticky",
        proxy_sticky_requests=3,
    )
    proxy_policy._reset_proxy_policy_state_for_tests()

    with (
        patch("infrastructure.access.proxy_policy.is_feature_enabled", return_value=True),
        patch("infrastructure.access.proxy_policy.get_store_profile", return_value=profile),
    ):
        m1 = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones",
        )
        m2 = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones?page=2",
        )

    assert m1.get("proxy") == m2.get("proxy")
    assert m1.get("access_proxy_mode") == "sticky"


def test_cooldown_skips_banned_proxy(tmp_path: Path) -> None:
    pool = tmp_path / "proxies.txt"
    _write_pool(pool, "http://8.8.8.8:8000", "http://9.9.9.9:9000")
    settings = Settings(
        PROXY_LIST_PATH=str(pool),
        SCRAPY_PROXY_POLICY_HARDENING_ENABLED=True,
        SCRAPY_PROXY_POLICY_DEFAULT_MODE="rotating",
        SCRAPY_PROXY_MAX_CONSECUTIVE_FAILURES=1,
        SCRAPY_PROXY_COOLDOWN_SECONDS_DEFAULT=3600,
        _env_file=None,
    )
    proxy_policy._reset_proxy_policy_state_for_tests()

    with patch("infrastructure.access.proxy_policy.is_feature_enabled", return_value=True):
        first = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones",
        )
        first_proxy = str(first.get("proxy") or "")
        assert first_proxy
        proxy_policy.mark_proxy_result(
            first_proxy,
            success=False,
            reason="captcha",
            settings=settings,
            store_name="mediapark",
        )
        second = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones?page=2",
        )

    assert second.get("proxy") != first_proxy


def test_store_specific_pool_path_override(tmp_path: Path) -> None:
    global_pool = tmp_path / "global_proxies.txt"
    store_pool = tmp_path / "store_proxies.txt"
    _write_pool(global_pool, "http://8.8.8.8:8000")
    _write_pool(store_pool, "http://9.9.9.9:9000")
    settings = Settings(
        PROXY_LIST_PATH=str(global_pool),
        SCRAPY_PROXY_POLICY_HARDENING_ENABLED=True,
        _env_file=None,
    )
    profile = StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        proxy_pool_path=str(store_pool),
    )
    proxy_policy._reset_proxy_policy_state_for_tests()

    with (
        patch("infrastructure.access.proxy_policy.is_feature_enabled", return_value=True),
        patch("infrastructure.access.proxy_policy.get_store_profile", return_value=profile),
    ):
        meta = proxy_policy.build_proxy_meta(
            "mediapark",
            "listing",
            settings=settings,
            target_url="https://mediapark.uz/products/category/phones",
        )

    assert meta.get("proxy") == "http://9.9.9.9:9000"
