from __future__ import annotations

from infrastructure.access.browser_policy import (
    build_browser_request_meta,
    get_playwright_launch_options,
    get_playwright_page_init_callback,
)


def test_build_browser_meta_has_playwright_and_goto():
    meta = build_browser_request_meta("uzum", "product")
    assert meta.get("playwright") is True
    assert "playwright_page_goto_kwargs" in meta
    assert meta["playwright_page_goto_kwargs"].get("timeout") == 45_000


def test_listing_timeout_shorter_than_product():
    m_listing = build_browser_request_meta("uzum", "listing")
    m_product = build_browser_request_meta("uzum", "product")
    assert m_listing["playwright_page_goto_kwargs"]["timeout"] < m_product["playwright_page_goto_kwargs"]["timeout"]


def test_playwright_init_callback_resolves():
    cb = get_playwright_page_init_callback()
    assert cb is None or callable(cb)


def test_launch_options_headless():
    assert get_playwright_launch_options("uzum")["headless"] is True
