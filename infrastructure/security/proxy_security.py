from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from domain.network_security import ProxySecurityDecision

from infrastructure.security.outbound_policy import (
    is_blocked_scheme,
    is_host_allowed,
    is_private_or_local_address,
    validate_outbound_url,
)


def mask_proxy_url(proxy_url: str) -> str:
    """Strip userinfo from proxy URL for logs."""
    raw = (proxy_url or "").strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw if "://" in raw else f"http://{raw}")
    except Exception:
        return "[invalid_proxy]"
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    scheme = p.scheme or "http"
    if p.username or p.password:
        return f"{scheme}://*:*@{host}{port}"
    return f"{scheme}://{host}{port}"


def is_proxy_host_allowed(proxy_url: str, settings: Any) -> bool:
    if not getattr(settings, "ENABLE_PROXY_HOST_VALIDATION", True):
        return True
    raw = (proxy_url or "").strip()
    if not raw:
        return False
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"http://{raw}"
    if is_blocked_scheme(raw, settings):
        return False
    try:
        p = urlparse(raw)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if is_private_or_local_address(host, settings):
        return False
    allowed = list(getattr(settings, "ALLOWED_PROXY_HOSTS", None) or [])
    if not allowed:
        return True
    return is_host_allowed(host, [str(x) for x in allowed])


def validate_proxy_url(proxy_url: str, settings: Any) -> ProxySecurityDecision:
    raw = (proxy_url or "").strip()
    if not raw:
        return ProxySecurityDecision(allowed=False, reason="empty_proxy_url")
    masked = mask_proxy_url(raw)
    if not is_proxy_host_allowed(raw, settings):
        return ProxySecurityDecision(allowed=False, proxy_url_masked=masked, reason="proxy_host_not_allowed")
    return ProxySecurityDecision(allowed=True, proxy_url_masked=masked)


def should_allow_proxy_for_target(proxy_url: str, target_url: str, settings: Any) -> bool:
    pv = validate_proxy_url(proxy_url, settings)
    if not pv.allowed:
        return False
    td = validate_outbound_url(target_url, settings)
    if not td.allowed:
        return False
    if td.target_type not in ("store", "unknown"):
        return False
    return True
