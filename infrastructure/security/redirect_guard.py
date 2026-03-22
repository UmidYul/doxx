from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urljoin

from domain.network_security import RedirectDecision

from infrastructure.security.outbound_policy import (
    _norm_host,
    is_private_or_local_address,
    validate_outbound_url,
)


def count_redirect_hops(chain: list[str]) -> int:
    return max(0, len(chain) - 1)


def can_follow_redirect(from_url: str, to_url: str, settings: Any) -> RedirectDecision:
    if not getattr(settings, "ENABLE_REDIRECT_HOST_VALIDATION", True):
        try:
            p1 = urlparse(from_url)
            p2 = urlparse(to_url)
            same = _norm_host(p1.netloc) == _norm_host(p2.netloc)
        except Exception:
            same = False
        return RedirectDecision(allowed=True, from_url=from_url, to_url=to_url, same_site=same)

    try:
        resolved_to = urljoin(from_url, to_url) if to_url else from_url
        p_from = urlparse(from_url)
        p_to = urlparse(resolved_to)
        h_from = _norm_host(p_from.hostname or "")
        h_to = _norm_host(p_to.hostname or "")
        same_site = h_from == h_to or (h_to.endswith("." + h_from) or h_from.endswith("." + h_to))
    except Exception:
        return RedirectDecision(
            allowed=False,
            from_url=from_url,
            to_url=to_url,
            reason="redirect_parse_error",
            same_site=False,
        )

    if is_private_or_local_address(h_to, settings):
        return RedirectDecision(
            allowed=False,
            from_url=from_url,
            to_url=resolved_to,
            reason="redirect_to_private_or_local",
            same_site=False,
        )

    d_to = validate_outbound_url(resolved_to, settings)
    if not d_to.allowed:
        return RedirectDecision(
            allowed=False,
            from_url=from_url,
            to_url=resolved_to,
            reason=d_to.reason or "redirect_target_rejected",
            same_site=same_site,
        )

    d_from = validate_outbound_url(from_url, settings)
    if d_from.target_type == "crm" and d_to.target_type != "crm":
        return RedirectDecision(
            allowed=False,
            from_url=from_url,
            to_url=resolved_to,
            reason="crm_redirect_to_non_crm_host",
            same_site=same_site,
        )
    if d_from.target_type == "store" and d_to.target_type not in ("store", "unknown"):
        return RedirectDecision(
            allowed=False,
            from_url=from_url,
            to_url=resolved_to,
            reason="store_redirect_to_non_store",
            same_site=same_site,
        )
    if d_from.target_type == "store" and d_to.target_type == "unknown":
        mode = (getattr(settings, "NETWORK_SECURITY_MODE", "restricted") or "restricted").strip().lower()
        if mode == "restricted":
            return RedirectDecision(
                allowed=False,
                from_url=from_url,
                to_url=resolved_to,
                reason="store_redirect_to_unknown_in_restricted_mode",
                same_site=same_site,
            )

    return RedirectDecision(
        allowed=True,
        from_url=from_url,
        to_url=resolved_to,
        reason=None,
        same_site=same_site,
    )


def validate_redirect_chain(urls: list[str], settings: Any) -> list[RedirectDecision]:
    out: list[RedirectDecision] = []
    max_hops = int(getattr(settings, "MAX_REDIRECT_HOPS", 5) or 5)
    if count_redirect_hops(urls) > max_hops:
        if urls:
            out.append(
                RedirectDecision(
                    allowed=False,
                    from_url=urls[0],
                    to_url=urls[-1],
                    reason=f"too_many_redirects>{max_hops}",
                    same_site=False,
                )
            )
        return out
    for i in range(len(urls) - 1):
        out.append(can_follow_redirect(urls[i], urls[i + 1], settings))
    return out
