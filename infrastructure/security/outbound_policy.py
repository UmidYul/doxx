from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from domain.network_security import HostValidationDecision, OutboundTargetType

_UNSAFE_SCHEMES = frozenset(
    {
        "file",
        "ftp",
        "ftps",
        "gopher",
        "ws",
        "wss",
        "javascript",
        "data",
        "vbscript",
    }
)

_LOCAL_HOSTNAMES = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "0000:0000:0000:0000:0000:0000:0000:0001",
    }
)

_METADATA_IPV4 = frozenset({"169.254.169.254"})
_METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata.goog"})

_SUSPICIOUS_HOST_SUFFIXES = (".local", ".internal", ".corp", ".lan")


def _network_mode(settings: Any) -> str:
    return (getattr(settings, "NETWORK_SECURITY_MODE", "restricted") or "restricted").strip().lower()


def _norm_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


def is_host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    h = _norm_host(host)
    if not h:
        return False
    for raw in allowed_hosts:
        a = _norm_host(str(raw))
        if not a:
            continue
        if h == a or h.endswith("." + a):
            return True
    return False


def _crm_configured_hosts(settings: Any) -> list[str]:
    pinned = list(getattr(settings, "ALLOWED_CRM_HOSTS", None) or [])
    if pinned:
        return [str(x).strip() for x in pinned if str(x).strip()]
    if getattr(settings, "ENABLE_CRM_HOST_PINNING", True):
        base = getattr(settings, "CRM_BASE_URL", "") or ""
        try:
            p = urlparse(base if "://" in base else f"https://{base}")
            h = _norm_host(p.hostname or "")
            return [h] if h else []
        except Exception:
            return []
    return []


def is_private_or_local_address(host: str, settings: Any | None = None) -> bool:
    s = settings
    h = _norm_host(host)
    if not h:
        return True
    if h in _LOCAL_HOSTNAMES:
        return True
    if h in _METADATA_HOSTS or h in _METADATA_IPV4:
        return True
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return True
        if (s is None or getattr(s, "BLOCK_METADATA_IPS", True)) and str(ip) in _METADATA_IPV4:
            return True
    except ValueError:
        pass
    if s is None or getattr(s, "BLOCK_PRIVATE_NETWORK_RANGES", True):
        try:
            # embedded IPv4 in hostname (rare)
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", h):
                ip = ipaddress.ip_address(h)
                return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
        except ValueError:
            pass
    return False


def is_blocked_scheme(url: str, settings: Any | None = None) -> bool:
    s = settings
    try:
        p = urlparse(url.strip())
    except Exception:
        return True
    scheme = (p.scheme or "").lower().strip()
    if not scheme:
        return False
    if scheme in ("http", "https"):
        return False
    if (s is None or getattr(s, "ENABLE_FILE_SCHEME_BLOCK", True)) and scheme == "file":
        return True
    if (s is None or getattr(s, "ENABLE_UNSAFE_SCHEME_BLOCK", True)) and scheme in _UNSAFE_SCHEMES:
        return True
    return scheme not in ("http", "https")


def classify_target_type(url: str, settings: Any) -> OutboundTargetType:
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return "unknown"
    host = _norm_host(p.hostname or "")
    if not host:
        return "unknown"
    if is_host_allowed(host, _crm_configured_hosts(settings)):
        return "crm"
    if is_host_allowed(host, list(getattr(settings, "ALLOWED_STORE_HOSTS", []) or [])):
        return "store"
    if is_host_allowed(host, list(getattr(settings, "ALLOWED_PROXY_HOSTS", []) or [])):
        return "proxy"
    return "unknown"


def validate_outbound_url(url: str, settings: Any) -> HostValidationDecision:
    """Full outbound validation for a URL (SSRF-style guardrails + allowlists)."""
    raw = (url or "").strip()
    if not raw:
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host="",
            reason="empty_url",
            matched_rule="empty",
        )

    if is_blocked_scheme(raw, settings):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host="",
            reason="blocked_or_unsafe_scheme",
            matched_rule="scheme_block",
        )

    try:
        p = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host="",
            reason="malformed_url",
            matched_rule="parse_error",
        )

    host = _norm_host(p.hostname or "")
    if not host:
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host="",
            reason="missing_host",
            matched_rule="no_host",
        )

    if getattr(settings, "ENABLE_LOCALHOST_BLOCK", True) and (
        host in _LOCAL_HOSTNAMES or host.startswith("127.") or host == "0.0.0.0"
    ):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host=host,
            reason="localhost_blocked",
            matched_rule="localhost",
        )

    if getattr(settings, "ENABLE_PRIVATE_IP_BLOCK", True) and is_private_or_local_address(host, settings):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host=host,
            reason="private_or_metadata_host",
            matched_rule="private_ip",
        )

    for suf in _SUSPICIOUS_HOST_SUFFIXES:
        if host.endswith(suf) and getattr(settings, "NETWORK_SECURITY_MODE", "restricted") == "restricted":
            return HostValidationDecision(
                allowed=False,
                target_type="unknown",
                host=host,
                reason="suspicious_internal_suffix",
                matched_rule="internal_suffix",
            )

    t = classify_target_type(raw, settings)
    mode = _network_mode(settings)

    if t == "crm":
        if getattr(settings, "ENABLE_CRM_HOST_PINNING", True):
            allowed = is_host_allowed(host, _crm_configured_hosts(settings))
            return HostValidationDecision(
                allowed=allowed,
                target_type="crm",
                host=host,
                reason=None if allowed else "crm_host_not_pinned",
                matched_rule="crm_allowlist" if allowed else None,
            )
        return HostValidationDecision(allowed=True, target_type="crm", host=host, matched_rule="crm_open")

    if t == "store":
        if getattr(settings, "ENABLE_STORE_HOST_PINNING", True) and getattr(
            settings, "ENABLE_OUTBOUND_HOST_ALLOWLIST", True
        ):
            allowed = is_host_allowed(host, list(getattr(settings, "ALLOWED_STORE_HOSTS", []) or []))
            return HostValidationDecision(
                allowed=allowed,
                target_type="store",
                host=host,
                reason=None if allowed else "store_host_not_allowlisted",
                matched_rule="store_allowlist" if allowed else None,
            )
        return HostValidationDecision(allowed=True, target_type="store", host=host, matched_rule="store_open")

    if t == "proxy":
        return HostValidationDecision(allowed=True, target_type="proxy", host=host, matched_rule="proxy_allowlist")

    # unknown
    if mode == "open":
        return HostValidationDecision(allowed=True, target_type="unknown", host=host, matched_rule="open_mode")
    return HostValidationDecision(
        allowed=False,
        target_type="unknown",
        host=host,
        reason="unknown_host_restricted_mode",
        matched_rule="restricted_unknown",
    )


def validate_store_crawl_url(url: str, store_name: str, settings: Any) -> HostValidationDecision:
    """Store spider outbound: must resolve to store target (or open mode)."""
    d = validate_outbound_url(url, settings)
    if not d.allowed:
        return d
    if d.target_type == "store":
        return d
    if d.target_type == "unknown" and _network_mode(settings) == "open":
        return d
    if d.target_type in ("crm", "proxy"):
        return HostValidationDecision(
            allowed=False,
            target_type=d.target_type,
            host=d.host,
            reason="store_crawl_target_must_be_store_host",
            matched_rule="wrong_target_type",
        )
    return d
