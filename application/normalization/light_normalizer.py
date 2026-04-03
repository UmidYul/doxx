from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from application.extractors.unit_normalizer import normalize_price

_WS_RE = re.compile(r"\s+")

# Max length for a single raw_specs value after sanitize
_MAX_SPEC_VALUE_LEN = 500

def _is_barcode_key(key: str) -> bool:
    k = key.strip().lower()
    if k in ("barcode", "ean", "ean13", "gtin", "upc"):
        return True
    if "штрихкод" in k:
        return True
    if re.fullmatch(r"ean[\s_-]?13", k):
        return True
    return False

# Category tokens to strip from model_name (whole-word where possible)
_MODEL_NOISE_WORDS = (
    "смартфон",
    "телефон",
    "smartphone",
    "mobile",
    "phone",
    "tv",
    "телевизор",
    "television",
    "laptop",
    "notebook",
    "ноутбук",
    "tablet",
    "планшет",
    "galaxy",  # often redundant with model number after
)

_TABLET_PAT = re.compile(
    r"(планшет|tablet|ipad|galaxy\s*tab|surface\s*pro)",
    re.IGNORECASE,
)
_PHONE_PAT = re.compile(
    r"(смартфон|телефон|smartphone|\biphone\b|pixel\s*\d)",
    re.IGNORECASE,
)
_LAPTOP_PAT = re.compile(
    r"(laptop|notebook|ноутбук|macbook|thinkpad|ultrabook)",
    re.IGNORECASE,
)
_TV_PAT = re.compile(r"(\btv\b|телевизор|television|oled|qled\s*tv)", re.IGNORECASE)
_ACCESSORY_PAT = re.compile(
    r"(чехол|case\b|кабель|cable|наушники|headphones|earbuds|зарядк|charger|adapter)",
    re.IGNORECASE,
)
_APPLIANCE_PAT = re.compile(
    r"(холодильник|стиральн|микроволнов|плита|oven|fridge|washing\s*machine|посудомо)",
    re.IGNORECASE,
)

_ALLOWED_CATEGORIES = frozenset(
    {"phone", "laptop", "tv", "tablet", "appliance", "accessory",
     "monitor", "gaming", "unknown"}
)


def normalize_title_whitespace(value: str | None) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def normalize_price_value(raw: str | None) -> int | None:
    """Parse price to int UZS (or other integer currency); no float on the wire."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    dec = normalize_price(s)
    if dec is None:
        return None
    return int(dec)


def normalize_stock_value(raw: object) -> bool | None:
    """Tri-state stock: True / False / None (unknown or empty)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 0:
            return False
        if raw == 1:
            return True
        return None
    if isinstance(raw, str):
        t = raw.strip().lower()
        if not t:
            return None
        if t in (
            "false",
            "0",
            "no",
            "нет",
            "n",
            "off",
            "out of stock",
            "out-of-stock",
            "недоступно",
            "нет в наличии",
        ):
            return False
        if t in (
            "true",
            "1",
            "yes",
            "y",
            "on",
            "есть",
            "available",
            "in stock",
            "in-stock",
            "да",
        ):
            return True
        return None
    return None


def sanitize_raw_specs(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        val = "" if v is None else str(v).strip()
        if not val:
            continue
        if len(val) > _MAX_SPEC_VALUE_LEN:
            val = val[:_MAX_SPEC_VALUE_LEN]
        if key not in out:
            out[key] = val
        elif not out[key] and val:
            out[key] = val
    return out


def extract_barcode(raw_specs: dict[str, str]) -> str | None:
    for k, v in raw_specs.items():
        if not _is_barcode_key(str(k)):
            continue
        digits = re.sub(r"\D", "", str(v))
        if len(digits) in (8, 12, 13, 14):
            return digits
    return None


def extract_model_name(
    title: str,
    brand: str | None = None,
    category_hint: str | None = None,
) -> str | None:
    t = normalize_title_whitespace(title)
    if not t:
        return None
    rest = t
    if brand:
        b = brand.strip()
        if b and rest.lower().startswith(b.lower()):
            rest = rest[len(b) :].strip()
            rest = rest.lstrip("-–—: ").strip()
    low = rest.lower()
    for w in _MODEL_NOISE_WORDS:
        if not w:
            continue
        if len(w) == 1:
            continue
        pattern = re.compile(rf"(?i)\b{re.escape(w)}\b")
        rest = pattern.sub(" ", rest)
    rest = _WS_RE.sub(" ", rest).strip()
    if len(rest) < 2:
        return None
    return rest


def _classify_from_text(text: str) -> str | None:
    if not text or not text.strip():
        return None
    t = text.lower()
    if _TABLET_PAT.search(t):
        return "tablet"
    if _LAPTOP_PAT.search(t):
        return "laptop"
    if _TV_PAT.search(t):
        return "tv"
    if _ACCESSORY_PAT.search(t):
        return "accessory"
    if _APPLIANCE_PAT.search(t):
        return "appliance"
    if _PHONE_PAT.search(t):
        return "phone"
    return None


def _normalize_spider_hint(hint: str | None) -> str | None:
    if not hint:
        return None
    h = hint.strip().lower()
    mapping = {
        "смартфон": "phone",
        "смартфоны": "phone",
        "телефон": "phone",
        "телефоны": "phone",
        "mobile": "phone",
        "phone": "phone",
        "планшет": "tablet",
        "планшеты": "tablet",
        "tablet": "tablet",
        "ноутбук": "laptop",
        "ноутбуки": "laptop",
        "laptop": "laptop",
        "notebook": "laptop",
        "телевизор": "tv",
        "телевизоры": "tv",
        "tv": "tv",
        "аксессуар": "accessory",
        "аксессуары": "accessory",
        "бытовая": "appliance",
        "техника": "appliance",
    }
    if h in mapping:
        return mapping[h]
    if "планшет" in h or "tablet" in h:
        return "tablet"
    if "ноутбук" in h or "laptop" in h or "notebook" in h:
        return "laptop"
    if "телевиз" in h or h == "tv":
        return "tv"
    if "смартфон" in h or "телефон" in h or "phone" in h:
        return "phone"
    if h in _ALLOWED_CATEGORIES:
        return h
    return None


def derive_category_hint(
    url: str,
    title: str,
    raw_specs: dict[str, str],
    spider_hint: str | None = None,
) -> str:
    """Return one of: phone, laptop, tv, tablet, appliance, accessory, unknown."""
    nh = _normalize_spider_hint(spider_hint)
    if nh:
        return nh

    try:
        path = (urlparse(url).path or "").lower()
    except Exception:
        path = ""
    from_url = _classify_from_text(path + " " + url.lower())
    if from_url:
        return from_url

    from_title = _classify_from_text(title)
    if from_title:
        return from_title

    blob = " ".join(f"{k} {v}" for k, v in raw_specs.items()).lower()
    from_specs = _classify_from_text(blob)
    if from_specs:
        return from_specs

    return "unknown"


def build_external_ids(store: str, source_id: str | None) -> dict[str, str]:
    sid = (source_id or "").strip()
    if not sid:
        return {}
    st = store.strip()
    if not st:
        return {}
    return {st: sid}


def normalize_image_urls(urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        s = str(u).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 10:
            break
    return out
