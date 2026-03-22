from __future__ import annotations

from typing import Any


def _non_empty_str(v: Any) -> bool:
    return bool(str(v or "").strip())


def _has_identity(item: dict[str, Any]) -> bool:
    sid = (item.get("source_id") or item.get("external_id") or "").strip()
    if sid:
        return True
    url = (item.get("url") or "").strip()
    return bool(url)


def missing_required_fields(item: dict[str, Any]) -> list[str]:
    """Fields required for a *usable* scraped product dict (pre-:class:`RawProduct`)."""
    missing: list[str] = []
    if not _non_empty_str(item.get("title") or item.get("name")):
        missing.append("title")
    if not _non_empty_str(item.get("url")):
        missing.append("url")
    if not _non_empty_str(item.get("source")):
        missing.append("source")
    if not _has_identity(item):
        missing.append("identity")
    return missing


def has_price_signal(item: dict[str, Any]) -> bool:
    if _non_empty_str(item.get("price_str")):
        return True
    pv = item.get("price_value")
    if pv is not None and str(pv).strip():
        return True
    return _non_empty_str(item.get("price_raw"))


def missing_recommended_fields(item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not has_price_signal(item):
        missing.append("price")  # any of price_str / price_raw / price_value
    if not _non_empty_str(item.get("brand")):
        missing.append("brand")
    imgs = item.get("image_urls") or []
    if not isinstance(imgs, list) or len(imgs) == 0:
        missing.append("image_urls")
    specs = item.get("raw_specs") or {}
    if not isinstance(specs, dict) or len(specs) == 0:
        missing.append("raw_specs")
    if not _non_empty_str(item.get("category_hint") or item.get("category")):
        missing.append("category_hint")
    return missing


def is_usable_product_item(item: dict[str, Any]) -> bool:
    """Usable = title + url + store + at least one identity signal (source_id or url path)."""
    return len(missing_required_fields(item)) == 0


def is_partial_product_item(item: dict[str, Any]) -> bool:
    """Partial = usable but missing one or more recommended fields."""
    if not is_usable_product_item(item):
        return False
    return len(missing_recommended_fields(item)) > 0
