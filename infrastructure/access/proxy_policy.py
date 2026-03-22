from __future__ import annotations

import logging
import os
from typing import Any

from config.settings import Settings, settings as app_settings
from infrastructure.access.store_profiles import get_store_profile

logger = logging.getLogger(__name__)


def is_proxy_available(settings: Settings | None = None) -> bool:
    s = settings or app_settings
    path = (s.PROXY_LIST_PATH or "").strip()
    if not path:
        return False
    if not os.path.isfile(path):
        logger.warning(
            "PROXY_LIST_PATH set but file missing (%s) — proxy disabled for this run",
            path,
        )
        return False
    return True


def _read_first_proxy_url(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError as exc:
        logger.warning("Could not read proxy list %s: %s", path, exc)
    return None


def should_install_rotating_proxy_middleware(settings: Settings | None = None) -> bool:
    """Register ``RotatingProxyMiddleware`` only when explicitly enabled and list is readable."""
    s = settings or app_settings
    if not getattr(s, "SCRAPY_ROTATING_PROXY_ENABLED", False):
        return False
    return is_proxy_available(s)


def should_enable_rotating_proxies(store_name: str, settings: Settings | None = None) -> bool:
    """Whether this store is configured to use the global rotating proxy pool (if installed)."""
    s = settings or app_settings
    if not getattr(s, "SCRAPY_ROTATING_PROXY_ENABLED", False):
        return False
    if not is_proxy_available(s):
        return False
    profile = get_store_profile(store_name)
    return profile.requires_proxy or profile.mode == "http_with_proxy"


def build_proxy_meta(store_name: str, purpose: str, settings: Settings | None = None) -> dict[str, Any]:
    """Per-request proxy meta; empty dict when proxy unavailable or not requested."""
    _ = purpose
    s = settings or app_settings
    profile = get_store_profile(store_name)
    if not profile.fallback_to_proxy and not profile.requires_proxy:
        return {}
    if not is_proxy_available(s):
        return {}
    url = _read_first_proxy_url(s.PROXY_LIST_PATH)
    if not url:
        logger.warning("Proxy list empty or unreadable — skipping proxy meta")
        return {}
    # Scrapy expects http://user:pass@host:port
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"
    from infrastructure.security import network_security_logger as net_log
    from infrastructure.security.proxy_security import validate_proxy_url

    pv = validate_proxy_url(url, s)
    if not pv.allowed:
        ph = ""
        if pv.proxy_url_masked:
            try:
                from urllib.parse import urlparse

                ph = (urlparse(pv.proxy_url_masked).hostname or "").strip()
            except Exception:
                ph = ""
        net_log.emit_proxy_blocked(
            reason=pv.reason or "proxy_rejected",
            proxy_host=ph or "[redacted]",
            store_name=store_name,
        )
        logger.warning("Proxy URL rejected by network policy (%s) — skipping proxy meta", pv.reason)
        return {}
    return {"proxy": url, "access_used_manual_proxy": True}
