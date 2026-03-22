from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from domain.network_security import HostValidationDecision

from infrastructure.security.outbound_policy import (
    is_blocked_scheme,
    is_private_or_local_address,
    validate_outbound_url,
    _norm_host,
)


def reject_if_suspicious_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return True
    if "\\\\" in raw:
        return True
    s = raw.strip()
    if s.startswith("//"):
        return True
    if re.search(r"[\x00-\x1f\x7f]", raw):
        return True
    try:
        p = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return True
    if p.username or p.password:
        return True
    if "%00" in raw.lower():
        return True
    return False


def reject_if_internal_target(url: str, settings: Any) -> bool:
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return True
    host = _norm_host(p.hostname or "")
    if not host:
        return True
    return is_private_or_local_address(host, settings)


def normalize_and_validate_url(url: str, settings: Any) -> HostValidationDecision:
    if reject_if_suspicious_url(url):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host=_norm_host(urlparse(url).hostname or "") if url else "",
            reason="suspicious_or_malformed_url",
            matched_rule="ssrf_suspicious",
        )
    if is_blocked_scheme(url, settings):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host="",
            reason="blocked_scheme",
            matched_rule="ssrf_scheme",
        )
    if reject_if_internal_target(url, settings):
        return HostValidationDecision(
            allowed=False,
            target_type="unknown",
            host=_norm_host(urlparse(url if "://" in url else f"https://{url}").hostname or ""),
            reason="internal_target",
            matched_rule="ssrf_internal",
        )
    return validate_outbound_url(url, settings)
