from __future__ import annotations

import re

from application.normalization.category_inference import infer_category_hint, normalize_category_signal
from application.normalization.price_normalization import normalize_price
from domain.stock_normalization import normalize_stock_signal

_WS_RE = re.compile(r"\s+")
_ACCESSORY_COMPAT_PAT = re.compile(r"(?i)(?<!\w)\u0434\u043b\u044f\b|\b(?:for|compatible\s+with|dlya)\b")

# Max length for a single raw_specs value after sanitize
_MAX_SPEC_VALUE_LEN = 500

# Category tokens to strip from model_name (whole-word where possible)
_MODEL_NOISE_WORDS = (
    "\u0441\u043c\u0430\u0440\u0442\u0444\u043e\u043d",
    "\u0442\u0435\u043b\u0435\u0444\u043e\u043d",
    "smartphone",
    "mobile",
    "phone",
    "tv",
    "\u0442\u0435\u043b\u0435\u0432\u0438\u0437\u043e\u0440",
    "television",
    "laptop",
    "notebook",
    "\u043d\u043e\u0443\u0442\u0431\u0443\u043a",
    "tablet",
    "\u043f\u043b\u0430\u043d\u0448\u0435\u0442",
    "galaxy",  # often redundant with model number after
)


def _is_barcode_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in ("barcode", "ean", "ean13", "gtin", "upc", "\u0448\u0442\u0440\u0438\u0445\u043a\u043e\u0434"):
        return True
    return bool(re.fullmatch(r"ean[\s_-]?13", normalized))


def normalize_title_whitespace(value: str | None) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def normalize_price_value(raw: str | None) -> int | None:
    """Parse price to int UZS (or other integer currency); no float on the wire."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    dec = normalize_price(text)
    if dec is None:
        return None
    return int(dec)


def normalize_stock_value(raw: object) -> bool | None:
    """Tri-state stock: True / False / None (unknown or empty)."""
    return normalize_stock_signal(raw)


def sanitize_raw_specs(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        normalized_value = "" if value is None else str(value).strip()
        if not normalized_value:
            continue
        if len(normalized_value) > _MAX_SPEC_VALUE_LEN:
            normalized_value = normalized_value[:_MAX_SPEC_VALUE_LEN]
        if normalized_key not in out:
            out[normalized_key] = normalized_value
        elif not out[normalized_key] and normalized_value:
            out[normalized_key] = normalized_value
    return out


def extract_barcode(raw_specs: dict[str, str]) -> str | None:
    for key, value in raw_specs.items():
        if not _is_barcode_key(str(key)):
            continue
        digits = re.sub(r"\D", "", str(value))
        if len(digits) in (8, 12, 13, 14):
            return digits
    return None


def extract_model_name(
    title: str,
    brand: str | None = None,
    category_hint: str | None = None,
) -> str | None:
    cleaned_title = normalize_title_whitespace(title)
    if not cleaned_title:
        return None
    if normalize_category_signal(category_hint) == "accessory" and _ACCESSORY_COMPAT_PAT.search(cleaned_title):
        return None

    rest = cleaned_title
    if brand:
        brand_text = brand.strip()
        if brand_text and rest.lower().startswith(brand_text.lower()):
            rest = rest[len(brand_text) :].strip()
            rest = rest.lstrip("-\u2013\u2014: ").strip()

    for word in _MODEL_NOISE_WORDS:
        if len(word) <= 1:
            continue
        rest = re.compile(rf"(?i)\b{re.escape(word)}\b").sub(" ", rest)

    rest = _WS_RE.sub(" ", rest).strip()
    if len(rest) < 2:
        return None
    return rest


def derive_category_hint(
    url: str,
    title: str,
    raw_specs: dict[str, str],
    spider_hint: str | None = None,
) -> str:
    """Return one of: phone, laptop, tv, tablet, appliance, accessory, unknown."""
    return infer_category_hint(url, title, raw_specs, spider_hint=spider_hint)


def build_external_ids(store: str, source_id: str | None) -> dict[str, str]:
    source = (source_id or "").strip()
    if not source:
        return {}
    store_name = store.strip()
    if not store_name:
        return {}
    return {store_name: source}


def normalize_image_urls(urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        text = str(url).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= 10:
            break
    return out
