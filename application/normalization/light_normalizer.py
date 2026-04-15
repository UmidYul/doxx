from __future__ import annotations

import re

from application.extractors.spec_label_normalizer import normalize_spec_label
from application.normalization.category_inference import infer_category_hint, normalize_category_signal
from application.normalization.price_normalization import normalize_price
from domain.stock_normalization import normalize_stock_signal

_WS_RE = re.compile(r"\s+")
_ACCESSORY_COMPAT_PAT = re.compile(r"(?i)(?<!\w)\u0434\u043b\u044f\b|\b(?:for|compatible\s+with|dlya)\b")
_COMPATIBILITY_VALUE_PREFIX_PAT = re.compile(
    r"(?i)^(?:"
    r"(?:\u0434\u043b\u044f|dlya|for)\b|"
    r"compatible\s+with\b|"
    r"\u0441\u043e\u0432\u043c\u0435\u0441\u0442\w*\s+\u0441\b|"
    r"\u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442\s+\u0434\u043b\u044f\b"
    r")\s*"
)
_COMPATIBILITY_SPLIT_PAT = re.compile(r"\s*(?:,|;|\||/|\band\b|\b\u0438\b)\s*|\s+\+\s+")
_COMPATIBILITY_LABEL_PREFIXES = (
    "compatibility",
    "compatible with",
    "compatible models",
    "compatible devices",
    "\u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c",
    "\u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c",
    "\u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442 \u0434\u043b\u044f",
)
_GENERIC_COMPAT_TARGETS = frozenset(
    {
        "iphone",
        "samsung",
        "xiaomi",
        "smartphone",
        "phone",
        "mobile phone",
        "телефон",
        "смартфон",
    }
)

_COMPAT_TRIM_CHARS = " -\u2013\u2014:;,./"
_BRAND_SPEC_LABELS = frozenset(
    {
        "brand",
        "\u0431\u0440\u0435\u043d\u0434",
        "manufacturer",
        "\u043f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c",
        "vendor",
    }
)
_MODEL_SPEC_LABELS = frozenset(
    {
        "model",
        "\u043c\u043e\u0434\u0435\u043b\u044c",
        "model name",
        "\u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u0438",
        "model number",
        "\u043a\u043e\u0434 \u043c\u043e\u0434\u0435\u043b\u0438",
        "product model",
    }
)
_UNKNOWN_TEXT_VALUES = frozenset(
    {
        "-",
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "not specified",
        "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e",
        "\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e",
        "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445",
        "\u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442",
    }
)

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


def _normalize_explicit_spec_value(value: object) -> str | None:
    text = normalize_title_whitespace(str(value or ""))
    if not text:
        return None
    if text.casefold() in _UNKNOWN_TEXT_VALUES:
        return None
    return text


def extract_brand_from_raw_specs(raw_specs: dict[str, object] | None) -> str | None:
    if not raw_specs:
        return None
    for raw_label, raw_value in raw_specs.items():
        label = normalize_spec_label(str(raw_label or ""))
        if label not in _BRAND_SPEC_LABELS:
            continue
        candidate = _normalize_explicit_spec_value(raw_value)
        if candidate:
            return candidate
    return None


def extract_model_name_from_raw_specs(
    raw_specs: dict[str, object] | None,
    *,
    brand: str | None = None,
    category_hint: str | None = None,
    compatibility_targets: list[str] | None = None,
) -> str | None:
    if not raw_specs:
        return None

    compat_norm = {
        normalize_title_whitespace(target).casefold()
        for target in (compatibility_targets or [])
        if normalize_title_whitespace(target)
    }
    for raw_label, raw_value in raw_specs.items():
        label = normalize_spec_label(str(raw_label or ""))
        if label not in _MODEL_SPEC_LABELS:
            continue
        candidate = _normalize_explicit_spec_value(raw_value)
        if not candidate:
            continue
        if (
            normalize_category_signal(category_hint) == "accessory"
            and candidate.casefold() in compat_norm
        ):
            continue
        normalized = extract_model_name(candidate, brand=brand, category_hint=category_hint)
        if normalized:
            return normalized
        return candidate
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


def _normalize_compatibility_label(label: object) -> str:
    text = normalize_title_whitespace(str(label or "")).casefold()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return _WS_RE.sub(" ", text).strip()


def _is_compatibility_label(label: object) -> bool:
    normalized = _normalize_compatibility_label(label)
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(prefix + " ")
        for prefix in _COMPATIBILITY_LABEL_PREFIXES
    )


def _extract_compatibility_tail(text: str, *, require_marker: bool) -> str:
    cleaned = normalize_title_whitespace(text)
    if not cleaned:
        return ""
    if require_marker:
        match = _ACCESSORY_COMPAT_PAT.search(cleaned)
        if not match:
            return ""
        return cleaned[match.end() :].strip(_COMPAT_TRIM_CHARS)
    return _COMPATIBILITY_VALUE_PREFIX_PAT.sub("", cleaned).strip(_COMPAT_TRIM_CHARS)


def _append_compatibility_targets(out: list[str], seen: set[str], text: str, *, require_marker: bool) -> None:
    tail = _extract_compatibility_tail(text, require_marker=require_marker)
    if len(tail) < 2:
        return
    for raw_part in _COMPATIBILITY_SPLIT_PAT.split(tail):
        candidate = normalize_title_whitespace(raw_part).strip(_COMPAT_TRIM_CHARS)
        if len(candidate) < 2:
            continue
        if candidate.casefold() in _GENERIC_COMPAT_TARGETS:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)


def extract_compatibility_targets(
    title: str,
    category_hint: str | None = None,
    raw_specs: dict[str, object] | None = None,
) -> list[str]:
    cleaned_title = normalize_title_whitespace(title)
    specs = dict(raw_specs or {})
    if not cleaned_title and not specs:
        return []

    effective_category = normalize_category_signal(category_hint)
    if not effective_category:
        effective_category = infer_category_hint("", cleaned_title, specs)

    has_title_signal = bool(_ACCESSORY_COMPAT_PAT.search(cleaned_title))
    has_specs_signal = any(_is_compatibility_label(key) for key in specs.keys())
    if effective_category != "accessory" and not (has_title_signal or has_specs_signal):
        return []

    seen: set[str] = set()
    out: list[str] = []
    if has_title_signal:
        _append_compatibility_targets(out, seen, cleaned_title, require_marker=True)
    for key, value in specs.items():
        if not _is_compatibility_label(key):
            continue
        _append_compatibility_targets(out, seen, str(value or ""), require_marker=False)
    return out


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
