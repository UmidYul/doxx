from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import scrapy.http

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import settings as app_settings
from infrastructure.access.store_profiles import get_store_profile

_HIDDEN_STYLE_RE = re.compile(r"(display\s*:\s*none|visibility\s*:\s*hidden)", re.I)
_DEFAULT_HONEYPOT_TOKENS: tuple[str, ...] = (
    "honeypot",
    "link-trap",
    "bot-trap",
    "crawler-trap",
    "hidden-link",
    "hp-link",
    "bait-link",
)


@dataclass(frozen=True)
class HoneypotFilterResult:
    """Result metadata for hidden/honeypot link filtering."""

    original_count: int
    kept_count: int
    dropped_count: int
    dropped_urls: tuple[str, ...]
    bypassed: bool
    reason: str | None = None


def _normalize_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


def _token_set(store_name: str) -> tuple[str, ...]:
    profile = get_store_profile(store_name)
    if profile.honeypot_tokens:
        cleaned = tuple(t.strip().lower() for t in profile.honeypot_tokens if str(t).strip())
        if cleaned:
            return cleaned
    return _DEFAULT_HONEYPOT_TOKENS


def _is_filter_enabled(store_name: str) -> bool:
    profile = get_store_profile(store_name)
    if profile.honeypot_filter_enabled is False:
        return False
    if profile.honeypot_filter_enabled is True:
        return True
    if not getattr(app_settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", False):
        return False
    return is_feature_enabled("honeypot_link_filter", store_name)


def _node_is_hidden(node, *, tokens: tuple[str, ...]) -> bool:
    attrs = {str(k).lower(): str(v) for k, v in (node.attrib or {}).items()}
    if "hidden" in attrs:
        return True
    aria_hidden = attrs.get("aria-hidden", "").strip().lower()
    if aria_hidden in {"true", "1", "yes"}:
        return True
    style = attrs.get("style", "")
    if style and _HIDDEN_STYLE_RE.search(style):
        return True
    joined = " ".join(
        [
            attrs.get("class", ""),
            attrs.get("id", ""),
            attrs.get("data-testid", ""),
            attrs.get("data-test", ""),
            attrs.get("data-qa", ""),
            attrs.get("rel", ""),
        ]
    ).lower()
    if joined and any(token in joined for token in tokens):
        return True
    return False


def _anchor_hidden(anchor_selector, *, tokens: tuple[str, ...]) -> bool:
    node = anchor_selector.root
    while node is not None:
        if _node_is_hidden(node, tokens=tokens):
            return True
        try:
            node = node.getparent()
        except Exception:
            node = None
    return False


def filter_honeypot_links(
    response: scrapy.http.Response,
    candidate_urls: list[str],
    *,
    store_name: str,
    link_kind: str,
) -> tuple[list[str], HoneypotFilterResult]:
    """Filter hidden/honeypot links while protecting against over-filtering."""
    original = list(candidate_urls)
    if not original:
        return original, HoneypotFilterResult(0, 0, 0, (), bypassed=False, reason=None)
    if not _is_filter_enabled(store_name):
        return original, HoneypotFilterResult(
            len(original),
            len(original),
            0,
            (),
            bypassed=False,
            reason="disabled",
        )

    normalized_candidates = {_normalize_url(response.urljoin(url)): None for url in original}
    visibility: dict[str, dict[str, bool]] = {
        url: {"visible": False, "hidden": False} for url in normalized_candidates
    }
    tokens = _token_set(store_name)

    for anchor in response.css("a[href]"):
        href = str(anchor.attrib.get("href") or "").strip()
        if not href:
            continue
        abs_url = _normalize_url(response.urljoin(href))
        if abs_url not in visibility:
            continue
        hidden = _anchor_hidden(anchor, tokens=tokens)
        if hidden:
            visibility[abs_url]["hidden"] = True
        else:
            visibility[abs_url]["visible"] = True

    kept: list[str] = []
    dropped: list[str] = []
    for url in original:
        normalized = _normalize_url(response.urljoin(url))
        info = visibility.get(normalized)
        if info is None:
            kept.append(url)
            continue
        if info["hidden"] and not info["visible"]:
            dropped.append(url)
            continue
        kept.append(url)

    dropped_count = len(dropped)
    original_count = len(original)
    if dropped_count == 0:
        return kept, HoneypotFilterResult(
            original_count,
            len(kept),
            0,
            (),
            bypassed=False,
            reason=None,
        )

    ratio = float(dropped_count) / float(max(1, original_count))
    max_ratio = float(getattr(app_settings, "SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO", 0.8))
    if original_count >= 3 and ratio > max_ratio:
        return original, HoneypotFilterResult(
            original_count,
            original_count,
            0,
            (),
            bypassed=True,
            reason=f"ratio_guard:{ratio:.2f}>{max_ratio:.2f}",
        )

    return kept, HoneypotFilterResult(
        original_count,
        len(kept),
        dropped_count,
        tuple(dropped),
        bypassed=False,
        reason=f"filtered_{link_kind}",
    )
