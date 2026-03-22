from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from domain.network_security import BrowserNavigationDecision

from infrastructure.security.outbound_policy import (
    _norm_host,
    is_blocked_scheme,
    is_private_or_local_address,
    validate_outbound_url,
    validate_store_crawl_url,
)


def should_block_cross_origin_navigation(parent_url: str | None, next_url: str, settings: Any) -> bool:
    if not getattr(settings, "ENABLE_BROWSER_SAME_ORIGIN_GUARD", True):
        return False
    if not parent_url:
        return False
    try:
        pp = urlparse(parent_url)
        np = urlparse(next_url)
        a = _norm_host(pp.hostname or "")
        b = _norm_host(np.hostname or "")
    except Exception:
        return True
    if a == b:
        return False
    if b.endswith("." + a) or a.endswith("." + b):
        return False
    allowed = list(getattr(settings, "ALLOWED_STORE_HOSTS", None) or [])
    from infrastructure.security.outbound_policy import is_host_allowed

    return not is_host_allowed(b, [str(x) for x in allowed])


def can_open_new_page(url: str, parent_url: str | None, settings: Any) -> BrowserNavigationDecision:
    raw = (url or "").strip()
    if is_blocked_scheme(raw, settings) or raw.lower().startswith("file:"):
        return BrowserNavigationDecision(
            allowed=False,
            url=raw,
            reason="blocked_scheme_or_file_navigation",
            requires_same_origin=True,
        )
    if is_private_or_local_address(_norm_host(urlparse(raw).hostname or ""), settings):
        return BrowserNavigationDecision(
            allowed=False,
            url=raw,
            reason="private_target",
            requires_same_origin=True,
        )
    if should_block_cross_origin_navigation(parent_url, raw, settings):
        return BrowserNavigationDecision(
            allowed=False,
            url=raw,
            reason="cross_origin_not_allowlisted",
            requires_same_origin=True,
        )
    return BrowserNavigationDecision(allowed=True, url=raw, requires_same_origin=False)


def validate_browser_navigation(url: str, store_name: str, settings: Any) -> BrowserNavigationDecision:
    _ = store_name
    d = validate_store_crawl_url(url, store_name, settings)
    if not d.allowed:
        return BrowserNavigationDecision(
            allowed=False,
            url=url,
            reason=d.reason,
            requires_same_origin=True,
        )
    if is_blocked_scheme(url, settings):
        return BrowserNavigationDecision(
            allowed=False,
            url=url,
            reason="unsafe_scheme",
            requires_same_origin=True,
        )
    du = validate_outbound_url(url, settings)
    if not du.allowed:
        return BrowserNavigationDecision(
            allowed=False,
            url=url,
            reason=du.reason,
            requires_same_origin=True,
        )
    return BrowserNavigationDecision(allowed=True, url=url, requires_same_origin=False)
