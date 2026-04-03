from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import orjson

_WS_RE = re.compile(r"\s+")


def normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = _WS_RE.sub(" ", str(value).replace("\xa0", " ")).strip()
    return text or None


def canonicalize_source_url(url: str) -> str:
    raw = normalize_text(url) or ""
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = (parts.netloc or "").lower()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def normalize_image_urls(image_urls: list[str] | tuple[str, ...] | None) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in image_urls or []:
        normalized = normalize_text(raw)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def normalize_json_dict(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        clean_key = normalize_text(key)
        if not clean_key:
            continue
        if isinstance(value, dict):
            out[clean_key] = normalize_json_dict(value)
            continue
        if isinstance(value, list):
            out[clean_key] = [normalize_text(item) if not isinstance(item, dict) else normalize_json_dict(item) for item in value]
            continue
        out[clean_key] = normalize_text(value)
    return out


def normalize_external_ids(payload: dict[str, Any] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (payload or {}).items():
        clean_key = normalize_text(key)
        clean_value = normalize_text(value)
        if not clean_key or not clean_value:
            continue
        normalized[clean_key] = clean_value
    return normalized


def build_product_identity_key(store_name: str, source_id: str | None, source_url: str) -> str:
    clean_store = (normalize_text(store_name) or "unknown").lower()
    clean_source_id = normalize_text(source_id)
    if clean_source_id:
        return f"{clean_store}:{clean_source_id}"
    digest = hashlib.sha256(canonicalize_source_url(source_url).encode("utf-8")).hexdigest()[:16]
    return f"{clean_store}:{digest}"


def build_scraped_payload_hash(
    *,
    store_name: str,
    source_url: str,
    source_id: str | None,
    title: str,
    brand: str | None,
    price_raw: str | None,
    in_stock: bool | None,
    raw_specs: dict[str, Any],
    image_urls: list[str],
    description: str | None,
    category_hint: str | None,
    external_ids: dict[str, str],
) -> str:
    blob = {
        "store_name": (normalize_text(store_name) or "").lower(),
        "source_url": canonicalize_source_url(source_url),
        "source_id": normalize_text(source_id),
        "title": (normalize_text(title) or "").lower(),
        "brand": (normalize_text(brand) or "").lower() or None,
        "price_raw": normalize_text(price_raw),
        "in_stock": in_stock,
        "raw_specs": normalize_json_dict(raw_specs),
        "image_urls": sorted(normalize_image_urls(image_urls)),
        "description": normalize_text(description),
        "category_hint": (normalize_text(category_hint) or "").lower() or None,
        "external_ids": dict(sorted(normalize_external_ids(external_ids).items())),
    }
    raw = orjson.dumps(blob, option=orjson.OPT_SORT_KEYS)
    return "sha256:" + hashlib.sha256(raw).hexdigest()

