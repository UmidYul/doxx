from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import unquote, urlparse

ALLOWED_CATEGORY_HINTS = frozenset(
    {"phone", "laptop", "tv", "tablet", "appliance", "accessory", "monitor", "gaming", "unknown"}
)

_WS_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"[_/\-|]+")

_DIRECT_HINT_MAP: dict[str, str] = {
    "phone": "phone",
    "phones": "phone",
    "mobile": "phone",
    "smartphone": "phone",
    "smartphones": "phone",
    "smartfon": "phone",
    "smartfony": "phone",
    "telefon": "phone",
    "telefony": "phone",
    "смартфон": "phone",
    "смартфоны": "phone",
    "телефон": "phone",
    "телефоны": "phone",
    "tablet": "tablet",
    "tablets": "tablet",
    "planshet": "tablet",
    "planshety": "tablet",
    "планшет": "tablet",
    "планшеты": "tablet",
    "laptop": "laptop",
    "laptops": "laptop",
    "notebook": "laptop",
    "notebooks": "laptop",
    "noutbuk": "laptop",
    "noutbuki": "laptop",
    "ноутбук": "laptop",
    "ноутбуки": "laptop",
    "tv": "tv",
    "television": "tv",
    "televizor": "tv",
    "televizory": "tv",
    "телевизор": "tv",
    "телевизоры": "tv",
    "accessory": "accessory",
    "accessories": "accessory",
    "aksessuar": "accessory",
    "aksessuary": "accessory",
    "аксессуар": "accessory",
    "аксессуары": "accessory",
    "appliance": "appliance",
    "appliances": "appliance",
    "bytovaya tehnika": "appliance",
    "бытовая техника": "appliance",
    "monitor": "monitor",
    "monitors": "monitor",
    "монитор": "monitor",
    "мониторы": "monitor",
    "gaming": "gaming",
    "игровой": "gaming",
    "игровые": "gaming",
    "unknown": "unknown",
}

_ACCESSORY_PAT = re.compile(
    r"\b(?:"
    r"аксессуар\w*|accessor(?:y|ies)|"
    r"чехол\w*|case(?:s)?|chehol\w*|"
    r"кабель\w*|kabel\w*|cable(?:s)?|"
    r"заряд(?:ка|ное|\w*)|zaryad\w*|charger(?:s)?|adapter(?:s)?|"
    r"power\s*bank|powerbank|"
    r"стекл\w*|steklo|пленк\w*|plenka|"
    r"наушник\w*|naushnik\w*|headphones?|earphones?|earbuds?|tws|гарнитур\w*|"
    r"держател\w*|holder|автодержател\w*|"
    r"ремеш\w*|remesh\w*|strap(?:s)?|"
    r"band(?:s)?|braslet\w*|браслет\w*|fitness\s*band(?:s)?|"
    r"watch(?:es)?|smart\s*watch(?:es)?|smart\s*chas\w*|"
    r"смарт\s*час\w*|умн\w*\s*час\w*|umn\w*\s*chas\w*|"
    r"ring(?:s)?|smart\s*ring(?:s)?|кол\w*ц\w*|kolc\w*|kolts\w*|"
    r"glasses|smart\s*glasses|очк\w*|ochki|"
    r"hydrogel"
    r")\b",
    re.IGNORECASE,
)
_TABLET_PAT = re.compile(
    r"\b(?:планшет\w*|planshet\w*|tablet(?:s)?|ipad|galaxy\s+tab|surface\s+pro)\b",
    re.IGNORECASE,
)
_LAPTOP_PAT = re.compile(
    r"\b(?:ноутбук\w*|noutbuk\w*|laptop(?:s)?|notebook(?:s)?|macbook|thinkpad|ultrabook)\b",
    re.IGNORECASE,
)
_TV_PAT = re.compile(
    r"\b(?:телевизор\w*|televizor\w*|television|smart\s+tv|tv|oled|qled)\b",
    re.IGNORECASE,
)
_MONITOR_PAT = re.compile(r"\b(?:монитор\w*|monitor(?:s)?|display(?:s)?)\b", re.IGNORECASE)
_GAMING_PAT = re.compile(
    r"\b(?:gaming|игров\w*|gamepad|controller|джойстик\w*|приставк\w*|playstation|xbox|nintendo)\b",
    re.IGNORECASE,
)
_APPLIANCE_PAT = re.compile(
    r"\b(?:"
    r"холодильник\w*|holodilnik\w*|refrigerator(?:s)?|fridge(?:s)?|"
    r"стиральн\w*|washing\s+machine(?:s)?|"
    r"посудомо\w*|dishwasher(?:s)?|"
    r"микроволнов\w*|microwave(?:s)?|"
    r"плита\w*|варочн\w*|"
    r"oven(?:s)?|духов\w*|"
    r"кондиционер\w*|konditsioner\w*|air\s+conditioner(?:s)?"
    r")\b",
    re.IGNORECASE,
)
_PHONE_PAT = re.compile(
    r"\b(?:смартфон\w*|телефон\w*|smartphone(?:s)?|smartfon\w*|telefon\w*|phone(?:s)?|"
    r"mobile(?:\s+phone)?|iphone|pixel\s*\d+)\b",
    re.IGNORECASE,
)

_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("accessory", _ACCESSORY_PAT),
    ("tablet", _TABLET_PAT),
    ("laptop", _LAPTOP_PAT),
    ("tv", _TV_PAT),
    ("monitor", _MONITOR_PAT),
    ("gaming", _GAMING_PAT),
    ("appliance", _APPLIANCE_PAT),
    ("phone", _PHONE_PAT),
)
_HARD_URL_CATEGORIES = frozenset({"accessory", "tablet", "laptop", "tv", "monitor", "gaming", "appliance"})


def _normalize_signal_text(value: str | None) -> str:
    text = unquote(str(value or "")).lower().replace("\xa0", " ")
    if not text:
        return ""
    text = _SEP_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return _WS_RE.sub(" ", text).strip()


def _classify_text(text: str | None) -> str | None:
    normalized = _normalize_signal_text(text)
    if not normalized:
        return None
    for category, pattern in _TEXT_PATTERNS:
        if pattern.search(normalized):
            return category
    return None


def _join_raw_specs(raw_specs: Mapping[str, object] | None) -> str:
    if not raw_specs:
        return ""
    parts: list[str] = []
    for key, value in raw_specs.items():
        key_s = str(key or "").strip()
        value_s = str(value or "").strip()
        if not key_s and not value_s:
            continue
        parts.append(f"{key_s} {value_s}".strip())
    return " ".join(parts)


def _classify_url(url: str | None) -> tuple[str | None, bool]:
    if not url:
        return None, False
    try:
        parsed = urlparse(str(url))
        raw = " ".join(part for part in (parsed.netloc, parsed.path, parsed.query, parsed.fragment) if part)
    except Exception:
        raw = str(url)
    category = _classify_text(raw)
    return category, bool(category and category in _HARD_URL_CATEGORIES)


def normalize_category_signal(hint: str | None) -> str | None:
    normalized = _normalize_signal_text(hint)
    if not normalized:
        return None
    if normalized in ALLOWED_CATEGORY_HINTS:
        return normalized
    if normalized in _DIRECT_HINT_MAP:
        return _DIRECT_HINT_MAP[normalized]
    squashed = normalized.replace(" ", "")
    if squashed in _DIRECT_HINT_MAP:
        return _DIRECT_HINT_MAP[squashed]
    return _classify_text(normalized)


def infer_category_hint(
    url: str,
    title: str,
    raw_specs: Mapping[str, object] | None = None,
    *,
    spider_hint: str | None = None,
) -> str:
    """Return the best-effort category using stable deterministic heuristics."""
    title_signal = _classify_text(title)
    specs_signal = _classify_text(_join_raw_specs(raw_specs))
    explicit_signals = [signal for signal in (title_signal, specs_signal) if signal]
    for category in ("accessory", "tablet", "laptop", "tv", "monitor", "gaming", "appliance", "phone"):
        if category in explicit_signals:
            return category

    url_signal, url_is_hard = _classify_url(url)
    if url_is_hard and url_signal:
        return url_signal

    hint_signal = normalize_category_signal(spider_hint)
    if hint_signal:
        return hint_signal

    if url_signal:
        return url_signal
    return "unknown"
