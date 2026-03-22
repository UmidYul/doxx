from __future__ import annotations

from config.settings import Settings
from infrastructure.security.browser_navigation_guard import (
    can_open_new_page,
    should_block_cross_origin_navigation,
    validate_browser_navigation,
)


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_cross_origin_blocked_unless_store_allowlisted() -> None:
    st = _s()
    assert should_block_cross_origin_navigation(
        "https://mediapark.uz/cat",
        "https://evil.com/p",
        st,
    )


def test_same_origin_not_blocked() -> None:
    st = _s()
    assert not should_block_cross_origin_navigation(
        "https://mediapark.uz/cat",
        "https://mediapark.uz/p/1",
        st,
    )


def test_can_open_new_page_allows_store_child_when_parent_store() -> None:
    st = _s()
    d = can_open_new_page(
        "https://mediapark.uz/p/1",
        "https://mediapark.uz/cat",
        st,
    )
    assert d.allowed


def test_can_open_new_page_blocks_file_scheme() -> None:
    st = _s()
    d = can_open_new_page("file:///tmp/x", None, st)
    assert not d.allowed


def test_validate_browser_navigation_respects_store_crawl() -> None:
    st = _s(NETWORK_SECURITY_MODE="restricted")
    d = validate_browser_navigation("https://evil.com/x", "mediapark", st)
    assert not d.allowed
