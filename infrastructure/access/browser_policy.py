from __future__ import annotations

from typing import Any, Callable

from infrastructure.access.store_profiles import get_store_profile


def get_playwright_page_init_callback() -> Callable[..., Any] | None:
    """Stealth + viewport integration (same as :class:`StealthMiddleware`)."""
    try:
        from infrastructure.middlewares.stealth_middleware import StealthMiddleware

        return StealthMiddleware._init_page
    except Exception:
        return None


def get_playwright_launch_options(store_name: str) -> dict[str, Any]:
    _ = store_name
    return {"headless": True}


def build_browser_request_meta(store_name: str, purpose: str) -> dict[str, Any]:
    """Meta fragment for scrapy-playwright (never global; spider must register handlers)."""
    _ = purpose
    profile = get_store_profile(store_name)
    if not profile.supports_browser and profile.mode != "browser_required":
        return {}

    timeout_ms = 45_000 if purpose == "product" else 35_000
    goto = {"wait_until": "domcontentloaded", "timeout": timeout_ms}

    cb = get_playwright_page_init_callback()
    meta: dict[str, Any] = {
        "playwright": True,
        "playwright_page_goto_kwargs": goto,
    }
    if cb is not None:
        meta["playwright_page_init_callback"] = cb
    return meta
