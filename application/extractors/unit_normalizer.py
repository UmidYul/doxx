from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

logger = logging.getLogger(__name__)

_INTEGER_TOKEN_RE = re.compile(r"\d+")
_DECIMAL_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _extract_single_integer_token(raw: str) -> int | None:
    tokens = _INTEGER_TOKEN_RE.findall(raw)
    if len(tokens) != 1:
        return None
    return int(tokens[0])


def _extract_single_decimal_token(raw: str) -> float | None:
    tokens = _DECIMAL_TOKEN_RE.findall(raw)
    if len(tokens) != 1:
        return None
    return float(tokens[0].replace(",", "."))

# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

_NEGOTIABLE_RE = re.compile(
    r"(?:по\s*договор[ёе]нности|по\s*запросу|narxi\s*kelishiladi"
    r"|цена\s*не\s*указана|bepul|бесплатно)",
    re.IGNORECASE,
)


def normalize_price(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw == "0":
        return None
    if _NEGOTIABLE_RE.search(raw):
        return None

    cleaned = re.sub(
        r"(?:сўм|сум|sum|uzs|руб\w*|₽|\$|€|£|¥)", "", raw, flags=re.IGNORECASE
    )

    cleaned = cleaned.replace(",", ".")

    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        if len(parts[-1]) <= 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)
    elif cleaned.count(".") == 1:
        after_dot = cleaned.split(".")[-1].strip()
        digits_after = re.sub(r"\D", "", after_dot)
        if len(digits_after) == 3:
            cleaned = cleaned.replace(".", "")

    cleaned = re.sub(r"[^\d.]", "", cleaned)

    if not cleaned or all(c in ".0" for c in cleaned):
        return None
    try:
        result = Decimal(cleaned)
        if result <= 0:
            return None
        return result
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Storage / RAM
# ---------------------------------------------------------------------------

_STORAGE_UNIT_FRAGMENT = "(?:TB|GB|\u0422\u0411|\u0442\u0431|\u0413\u0411|\u0433\u0431)"
_STORAGE_RE = re.compile(rf"(\d+)\s*({_STORAGE_UNIT_FRAGMENT})", re.IGNORECASE)
_STORAGE_COMPOSITE_RE = re.compile(
    rf"(?:\d+\s*{_STORAGE_UNIT_FRAGMENT}\s*(?:[-/+])\s*\d+(?:\s*{_STORAGE_UNIT_FRAGMENT})?"
    rf"|\d+\s*(?:[-/+])\s*\d+\s*{_STORAGE_UNIT_FRAGMENT})",
    re.IGNORECASE,
)


def normalize_storage(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if _STORAGE_COMPOSITE_RE.search(raw):
        return None

    matches = list(_STORAGE_RE.finditer(raw))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        val = int(matches[0].group(1))
        unit = matches[0].group(2).lower()
        if unit in ("tb", "\u0442\u0431"):
            return val * 1024
        return val

    plain = _extract_single_integer_token(raw)
    if plain is not None:
        return plain
    return None


def normalize_ram(raw: str | None) -> int | None:
    if raw is None:
        return None
    result = normalize_storage(raw)
    if result is not None and result > 64:
        logger.warning(
            "[SPEC_SANITY_SWAP] RAM value %d looks like storage, returning None",
            result,
        )
        return None
    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

_DISPLAY_CM_FRAGMENT = "(?:cm|\u0441\u043c)"
_DISPLAY_INCH_FRAGMENT = "(?:inch\\w*|\u0434\u044e\u0439\u043c\\w*|\"|\u2033|'')"
_CM_PATTERN = re.compile(rf"(\d+[.,]?\d*)\s*{_DISPLAY_CM_FRAGMENT}", re.IGNORECASE)
_INCH_PATTERN = re.compile(rf"(\d+[.,]?\d*)\s*{_DISPLAY_INCH_FRAGMENT}", re.IGNORECASE)
_DISPLAY_SHARED_UNIT_COMPOSITE_RE = re.compile(
    rf"\d+(?:[.,]\d+)?\s*(?:[-/+])\s*\d+(?:[.,]\d+)?\s*(?:{_DISPLAY_CM_FRAGMENT}|{_DISPLAY_INCH_FRAGMENT})",
    re.IGNORECASE,
)
_DISPLAY_DIMENSION_RE = re.compile(r"\d+(?:[.,]\d+)?\s*[xX\u0445\u0425\u00D7]\s*\d+(?:[.,]\d+)?")


def normalize_display(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if _DISPLAY_SHARED_UNIT_COMPOSITE_RE.search(raw):
        return None

    inch_matches = list(_INCH_PATTERN.finditer(raw))
    if len(inch_matches) > 1:
        return None
    if len(inch_matches) == 1:
        val = float(inch_matches[0].group(1).replace(",", "."))
        if 1.0 <= val <= 100.0:
            return val
        return None

    cm_matches = list(_CM_PATTERN.finditer(raw))
    if len(cm_matches) > 1:
        return None
    if len(cm_matches) == 1:
        val = float(cm_matches[0].group(1).replace(",", "."))
        val = round(val / 2.54, 1)
        if 1.0 <= val <= 100.0:
            return val
        return None

    if _DISPLAY_DIMENSION_RE.search(raw):
        return None

    val = _extract_single_decimal_token(raw)
    if val is not None and 1.0 <= val <= 100.0:
        return val
    return None


# ---------------------------------------------------------------------------
# Battery (phone, mAh)
# ---------------------------------------------------------------------------

_BATTERY_UNIT_FRAGMENT = "(?:mAh|mah|\u043c\u0410\u0447|\u043c\u0430\u0447)"
_BATTERY_RE = re.compile(rf"(\d{{3,5}})\s*{_BATTERY_UNIT_FRAGMENT}", re.IGNORECASE)
_BATTERY_COMPOSITE_RE = re.compile(
    rf"(?:\d{{3,5}}\s*{_BATTERY_UNIT_FRAGMENT}\s*(?:[-/+])\s*\d{{3,5}}(?:\s*{_BATTERY_UNIT_FRAGMENT})?"
    rf"|\d{{3,5}}\s*(?:[-/+])\s*\d{{3,5}}\s*{_BATTERY_UNIT_FRAGMENT})",
    re.IGNORECASE,
)


def normalize_battery(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if _BATTERY_COMPOSITE_RE.search(raw):
        return None

    matches = list(_BATTERY_RE.finditer(raw))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        val = int(matches[0].group(1))
        if 500 <= val <= 20000:
            return val
        return None

    plain = _extract_single_integer_token(raw)
    if plain is not None:
        val = int(plain)
        if 500 <= val <= 20000:
            return val
    return None


# ---------------------------------------------------------------------------
# Battery (laptop, Wh)
# ---------------------------------------------------------------------------

_BATTERY_WH_UNIT_FRAGMENT = "(?:Wh|wh|\u0412\u0442\\s*[\\xb7*\\u22c5]?\\s*\u0447|\u0412\u0442\u0447)"
_BATTERY_WH_RE = re.compile(rf"(\d+[.,]?\d*)\s*{_BATTERY_WH_UNIT_FRAGMENT}", re.IGNORECASE)
_BATTERY_WH_COMPOSITE_RE = re.compile(
    rf"(?:\d+(?:[.,]\d+)?\s*{_BATTERY_WH_UNIT_FRAGMENT}\s*(?:[-/+])\s*\d+(?:[.,]\d+)?(?:\s*{_BATTERY_WH_UNIT_FRAGMENT})?"
    rf"|\d+(?:[.,]\d+)?\s*(?:[-/+])\s*\d+(?:[.,]\d+)?\s*{_BATTERY_WH_UNIT_FRAGMENT})",
    re.IGNORECASE,
)


def normalize_battery_wh(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if _BATTERY_WH_COMPOSITE_RE.search(raw):
        return None

    matches = list(_BATTERY_WH_RE.finditer(raw))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        val = float(matches[0].group(1).replace(",", "."))
        if 10.0 <= val <= 200.0:
            return round(val, 1)

    plain = _extract_single_decimal_token(raw)
    if plain is not None:
        val = float(plain)
        if 10.0 <= val <= 200.0:
            return round(val, 1)
    return None


# ---------------------------------------------------------------------------
# Weight (grams — phones)
# ---------------------------------------------------------------------------

_KG_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*(?:кг|kg)", re.IGNORECASE)
_G_PATTERN = re.compile(
    r"(\d+[.,]?\d*)\s*(?:г(?!б|Б)|g(?!b|B)|грамм\w*|gram\w*)", re.IGNORECASE
)


def normalize_weight_g(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    m = _KG_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        result = int(val * 1000)
        if 50 <= result <= 50000:
            return result
        return None

    m = _G_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        result = int(val)
        if 50 <= result <= 50000:
            return result
    return None


# ---------------------------------------------------------------------------
# Weight (kg — laptops / appliances)
# ---------------------------------------------------------------------------


def normalize_weight_kg(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    m = _KG_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        if 0.1 <= val <= 50.0:
            return round(val, 2)
        return None

    m = _G_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        result = round(val / 1000, 2)
        if 0.1 <= result <= 50.0:
            return result
    return None


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

BRAND_ALIASES: dict[str, str] = {
    "эпл": "Apple", "apple": "Apple",
    "самсунг": "Samsung", "samsung": "Samsung",
    "сяоми": "Xiaomi", "xiaomi": "Xiaomi", "redmi": "Xiaomi",
    "хуавей": "Huawei", "huawei": "Huawei", "honor": "Honor",
    "реалми": "Realme", "realme": "Realme",
    "поко": "Poco", "poco": "Poco",
    "ванплас": "OnePlus", "oneplus": "OnePlus",
    "нокия": "Nokia", "nokia": "Nokia",
    "сони": "Sony", "sony": "Sony",
    "лг": "LG", "lg": "LG",
    "оппо": "Oppo", "oppo": "Oppo",
    "виво": "Vivo", "vivo": "Vivo",
    "гугл": "Google", "google": "Google",
    "моторола": "Motorola", "motorola": "Motorola",
    "зте": "ZTE", "zte": "ZTE",
    "текно": "Tecno", "tecno": "Tecno",
    "инфиникс": "Infinix", "infinix": "Infinix",
    "итель": "Itel", "itel": "Itel",
    "nothing": "Nothing",
    "iphone": "Apple",
    "novey": "Novey",
    "benco": "Benco",
    "hmd": "HMD",
    "blackview": "Blackview",
    "oukitel": "Oukitel",
    "doogee": "Doogee",
    "umidigi": "Umidigi",
    "cubot": "Cubot",
    "ulefone": "Ulefone",
    "coolpad": "Coolpad",
    "fly": "Fly", "флай": "Fly",
    "alcatel": "Alcatel", "алкатель": "Alcatel",
    "meizu": "Meizu", "мейзу": "Meizu",
    "hotwav": "Hotwav",
    "oscal": "Oscal",
    "agm": "AGM",
    "cat": "CAT",
    "асус": "ASUS", "asus": "ASUS",
    "леново": "Lenovo", "lenovo": "Lenovo",
    "делл": "Dell", "dell": "Dell",
    "эйсер": "Acer", "acer": "Acer",
    "хп": "HP", "hp": "HP",
}


def normalize_brand(raw: str | None, aliases: dict | None = None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    merged = {**BRAND_ALIASES}
    if aliases:
        merged.update({k.lower(): v for k, v in aliases.items()})

    key = raw.lower().strip()
    result = merged.get(key)
    if result:
        return result
    return raw.title()


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

_PROCESSOR_ALIASES: dict[str, str] | None = None


def _load_processor_aliases() -> dict[str, str]:
    global _PROCESSOR_ALIASES
    if _PROCESSOR_ALIASES is not None:
        return _PROCESSOR_ALIASES
    aliases_path = (
        Path(__file__).resolve().parent.parent.parent
        / "config"
        / "processor_aliases.json"
    )
    try:
        with open(aliases_path, encoding="utf-8") as f:
            _PROCESSOR_ALIASES = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Could not load processor_aliases.json from %s", aliases_path)
        _PROCESSOR_ALIASES = {}
    return _PROCESSOR_ALIASES


def normalize_processor(raw: str | None, aliases: dict | None = None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if aliases is None:
        aliases = _load_processor_aliases()

    if raw in aliases:
        return aliases[raw]

    lower = raw.lower()
    for key, val in aliases.items():
        if key.lower() == lower:
            return val

    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned if cleaned else None


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

COLOR_MAP: dict[str, str] = {
    "чёрный": "Black", "черный": "Black", "qora": "Black", "black": "Black",
    "белый": "White", "oq": "White", "white": "White",
    "синий": "Blue", "ko'k": "Blue", "blue": "Blue", "голубой": "Blue",
    "красный": "Red", "qizil": "Red", "red": "Red",
    "зелёный": "Green", "зеленый": "Green", "yashil": "Green", "green": "Green",
    "серый": "Gray", "kulrang": "Gray", "gray": "Gray", "grey": "Gray",
    "золотой": "Gold", "oltin": "Gold", "gold": "Gold",
    "розовый": "Pink", "pushti": "Pink", "pink": "Pink",
    "фиолетовый": "Purple", "binafsha": "Purple", "purple": "Purple",
    "серебристый": "Silver", "kumush": "Silver", "silver": "Silver",
    "оранжевый": "Orange", "to'q sariq": "Orange", "orange": "Orange",
    "жёлтый": "Yellow", "желтый": "Yellow", "sariq": "Yellow", "yellow": "Yellow",
    "бежевый": "Beige", "beige": "Beige",
    "коричневый": "Brown", "jigarrang": "Brown", "brown": "Brown",
    "бирюзовый": "Turquoise", "turquoise": "Turquoise",
    "лавандовый": "Lavender", "lavender": "Lavender",
    "бордовый": "Burgundy", "burgundy": "Burgundy",
    "мятный": "Mint", "mint": "Mint",
    "графитовый": "Graphite", "graphite": "Graphite",
    "тёмно-синий": "Navy", "темно-синий": "Navy", "navy": "Navy",
    "коралловый": "Coral", "coral": "Coral",
    "кремовый": "Cream", "cream": "Cream",
    "титановый": "Titanium", "titanium": "Titanium",
    "песочный": "Sand", "sand": "Sand",
}


def normalize_color(raw: str | None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    key = raw.lower().strip()
    result = COLOR_MAP.get(key)
    if result:
        return result
    return raw.title()


# ---------------------------------------------------------------------------
# Camera (MP)
# ---------------------------------------------------------------------------

_CAMERA_UNIT_FRAGMENT = "(?:MP|Mp|mp|\u041c\u043f|\u043c\u043f|\u043c\u0435\u0433\u0430\u043f\u0438\u043a\u0441\u0435\u043b\\w*|megapixel\\w*)"
_CAMERA_RE = re.compile(rf"(\d+)\s*{_CAMERA_UNIT_FRAGMENT}", re.IGNORECASE)
_CAMERA_COMPOSITE_RE = re.compile(
    rf"(?:\d+\s*{_CAMERA_UNIT_FRAGMENT}\s*(?:[-/+])\s*\d+(?:\s*{_CAMERA_UNIT_FRAGMENT})?"
    rf"|\d+\s*(?:[-/+])\s*\d+\s*{_CAMERA_UNIT_FRAGMENT})",
    re.IGNORECASE,
)
_CAMERA_LAYOUT_HINT_RE = re.compile(
    "(?:main|rear|back|front|selfie|wide|ultra|macro|depth|tele|"
    "\u043e\u0441\u043d\u043e\u0432\u043d\\w*|\u0442\u044b\u043b\u043e\u0432\\w*|"
    "\u0437\u0430\u0434\u043d\\w*|\u043f\u0435\u0440\u0435\u0434\u043d\\w*|\u0441\u0435\u043b\u0444\u0438)",
    re.IGNORECASE,
)


def normalize_camera_mp(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if _CAMERA_COMPOSITE_RE.search(raw):
        return None
    if (
        _CAMERA_LAYOUT_HINT_RE.search(raw)
        and re.search(r"[-/+]", raw)
        and len(_INTEGER_TOKEN_RE.findall(raw)) > 1
    ):
        return None

    matches = list(_CAMERA_RE.finditer(raw))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        val = int(matches[0].group(1))
        if 1 <= val <= 200:
            return val
        return None

    plain = _extract_single_integer_token(raw)
    if plain is not None and 1 <= plain <= 200:
        return plain
    return None


# ---------------------------------------------------------------------------
# SIM count
# ---------------------------------------------------------------------------


_SIM_DUAL_RE = re.compile(
    r"(?:\bdual\b|\bduos\b|\bikki\b|\bдва\b|\b2\s*(?:sim|slots?|nano[-\s]?sim|micro[-\s]?sim|mini[-\s]?sim|e[-\s]?sim)\b)",
    re.IGNORECASE,
)
_SIM_SINGLE_RE = re.compile(
    r"(?:\bsingle\b|\bbitta\b|\bодин\b|\b1\s*(?:sim|slot)\b)",
    re.IGNORECASE,
)
_SIM_COUNT_RE = re.compile(r"\b([1-4])\s*(?:sim|slots?|slot)\b", re.IGNORECASE)
_SIM_TOKEN_RE = re.compile(r"\b(?:e[-\s]?sim|nano[-\s]?sim|micro[-\s]?sim|mini[-\s]?sim)\b", re.IGNORECASE)


def normalize_sim_count(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if _SIM_DUAL_RE.search(text):
        return 2
    if _SIM_SINGLE_RE.search(text):
        return 1
    m = _SIM_COUNT_RE.search(text)
    if m:
        return int(m.group(1))

    tokens = _SIM_TOKEN_RE.findall(text)
    if len(tokens) >= 2:
        return min(len(tokens), 4)
    if len(tokens) == 1:
        return 1
    return None


# ---------------------------------------------------------------------------
# Boolean
# ---------------------------------------------------------------------------

_TRUE_VALUES = frozenset({
    "да", "есть", "yes", "true", "бор", "mavjud", "✓", "+", "1",
    "ха", "ha", "имеется", "поддерживается", "supported", "бар",
})
_FALSE_VALUES = frozenset({
    "нет", "no", "false", "йўқ", "yo'q", "yoq", "отсутствует",
    "0", "-", "не поддерживается", "unsupported",
})
_TRUE_BOOL_RE = re.compile(
    r"(?<!\w)(?:\u0434\u0430|\u0435\u0441\u0442\u044c|yes|true|\u0445\u0430|ha|\u0438\u043c\u0435\u0435\u0442\u0441\u044f|\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f|supported|mavjud|bar|bor)(?!\w)",
    re.IGNORECASE,
)
_FALSE_BOOL_RE = re.compile(
    r"(?<!\w)(?:\u043d\u0435\u0442|no|false|\u0439\u045e\u049b|yo'?q|\u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442|unsupported|\u043d\u0435\s+\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f)(?!\w)",
    re.IGNORECASE,
)
_BOOL_UNKNOWN_RE = re.compile(
    r"(?:\b(?:n/?a|unknown|not\s+specified|none)\b|\u043d\u0435\s+\u0443\u043a\u0430\u0437\u0430\u043d\u043e|\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e)",
    re.IGNORECASE,
)
_WIFI_CAPABILITY_RE = re.compile(r"(?:\bwi-?fi\b|802\.11|\b[256](?:\.\d+)?\s*ghz\b)", re.IGNORECASE)
_BLUETOOTH_CAPABILITY_RE = re.compile(r"(?:\bbluetooth\b|\bbt\b)", re.IGNORECASE)
_BLUETOOTH_VERSION_RE = re.compile(r"^v?\s*\d(?:\.\d+){0,2}$", re.IGNORECASE)
_HDMI_CAPABILITY_RE = re.compile(
    r"(?:\bhdmi\b|\b[1-9]\d*\s*(?:ports?|inputs?|port|input)\b|\b[1-9]\d*\s*(?:\u043f\u043e\u0440\u0442\w*|\u0440\u0430\u0437\u044a\u0435\u043c\w*)\b)",
    re.IGNORECASE,
)
_POSITIVE_INTEGER_RE = re.compile(r"^[1-9]\d*$")
_NFC_CAPABILITY_RE = re.compile(r"\bnfc\b", re.IGNORECASE)


def normalize_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    if _FALSE_BOOL_RE.search(text):
        return False
    if _TRUE_BOOL_RE.search(text):
        return True
    return None


def _infer_boolean_feature(field_name: str, raw_value: str) -> bool | None:
    text = raw_value.strip().lower()
    if not text or _BOOL_UNKNOWN_RE.search(text):
        return None
    if field_name == "has_wifi":
        return True if _WIFI_CAPABILITY_RE.search(text) else None
    if field_name == "has_bluetooth":
        if _BLUETOOTH_CAPABILITY_RE.search(text) or _BLUETOOTH_VERSION_RE.fullmatch(text):
            return True
        return None
    if field_name == "hdmi":
        if _HDMI_CAPABILITY_RE.search(text) or _POSITIVE_INTEGER_RE.fullmatch(text):
            return True
        return None
    if field_name == "nfc":
        return True if _NFC_CAPABILITY_RE.search(text) else None
    return None


# ---------------------------------------------------------------------------
# Smart TV (bool — platform names count as True)
# ---------------------------------------------------------------------------

_SMART_TV_PLATFORMS = frozenset({
    "android tv", "tizen", "webos", "google tv", "vidaa",
    "smart tv", "roku", "fire tv", "lg tv", "samsung tv",
    "яндекс тв", "салют тв",
})


def normalize_smart_tv(raw: str | None) -> bool | None:
    if raw is None:
        return None
    raw = raw.strip().lower()
    if not raw:
        return None
    if any(platform in raw for platform in _SMART_TV_PLATFORMS):
        return True
    return normalize_bool(raw)


# ---------------------------------------------------------------------------
# Refresh rate (Hz)
# ---------------------------------------------------------------------------

_HZ_UNIT_FRAGMENT = "(?:Hz|hz|\u0413\u0446|\u0433\u0446|\u0433\u0435\u0440\u0446)"
_HZ_RE = re.compile(rf"(\d+)\s*{_HZ_UNIT_FRAGMENT}", re.IGNORECASE)
_HZ_COMPOSITE_RE = re.compile(
    rf"(?:\d+\s*{_HZ_UNIT_FRAGMENT}\s*(?:[-/+])\s*\d+(?:\s*{_HZ_UNIT_FRAGMENT})?"
    rf"|\d+\s*(?:[-/+])\s*\d+\s*{_HZ_UNIT_FRAGMENT})",
    re.IGNORECASE,
)
_HZ_AMBIGUOUS_RE = re.compile(
    "(?:\\bup\\s*to\\b|\\bmax(?:imum)?\\b|\\bдо\\b|\\bмакс(?:имум)?\\b)",
    re.IGNORECASE,
)

_KNOWN_RATES = frozenset({24, 30, 50, 60, 75, 90, 120, 144, 165, 240})


def normalize_refresh_rate(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if _HZ_AMBIGUOUS_RE.search(raw) or _HZ_COMPOSITE_RE.search(raw):
        return None

    matches = list(_HZ_RE.finditer(raw))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        return int(matches[0].group(1))

    plain = _extract_single_integer_token(raw)
    if plain is not None:
        val = int(plain)
        if val in _KNOWN_RATES:
            return val
    return None


# ---------------------------------------------------------------------------
# Power (W)
# ---------------------------------------------------------------------------

_POWER_RE = re.compile(r"(\d+)\s*(?:Вт|W|вт|w)\b", re.IGNORECASE)


_POWER_TOKEN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:Р’С‚|W|РІС‚|w)\b", re.IGNORECASE)
_POWER_RANGE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*[-–—/]\s*\d+(?:[.,]\d+)?\s*(?:Р’С‚|W|РІС‚|w)\b",
    re.IGNORECASE,
)
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def normalize_power_w(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if _POWER_RANGE_RE.search(text):
        return None
    matches = _POWER_TOKEN_RE.findall(text)
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        value = float(matches[0].replace(",", "."))
        return int(value) if value.is_integer() and value > 0 else None
    if _PLAIN_NUMBER_RE.fullmatch(text):
        value = float(text.replace(",", "."))
        return int(value) if value.is_integer() and value > 0 else None
    return None


# ---------------------------------------------------------------------------
# Volume (litres)
# ---------------------------------------------------------------------------

_VOLUME_RE = re.compile(
    r"(\d+[.,]?\d*)\s*(?:л(?!с)|l(?!b)|литр\w*|litr\w*)\b", re.IGNORECASE
)


_VOLUME_RANGE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*[-–—/]\s*\d+(?:[.,]\d+)?\s*(?:Р»(?!СЃ)|l(?!b)|Р»РёС‚СЂ\w*|litr\w*)\b",
    re.IGNORECASE,
)
_VOLUME_ML_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:ml|мл)\b", re.IGNORECASE)


def normalize_volume_l(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if _VOLUME_RANGE_RE.search(text) or re.search(r"\d+(?:[.,]\d+)?\s*[-–—/]\s*\d+(?:[.,]\d+)?", text):
        return None
    litre_matches = _VOLUME_RE.findall(text)
    ml_matches = _VOLUME_ML_RE.findall(text)
    if len(litre_matches) + len(ml_matches) > 1:
        return None
    if len(litre_matches) == 1:
        return float(litre_matches[0].replace(",", "."))
    if len(ml_matches) == 1:
        return round(float(ml_matches[0].replace(",", ".")) / 1000, 3)
    if _PLAIN_NUMBER_RE.fullmatch(text):
        return float(text.replace(",", "."))
    return None


# ---------------------------------------------------------------------------
# Energy class
# ---------------------------------------------------------------------------

_ENERGY_CLASS_RE = re.compile(r"([A-Da-d]\+{0,3})")


def normalize_energy_class(raw: str | None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _ENERGY_CLASS_RE.search(raw)
    if m:
        return m.group(0).strip().upper()
    return raw.strip().upper() if raw.strip() else None


# ---------------------------------------------------------------------------
# Warranty (months)
# ---------------------------------------------------------------------------

_WARRANTY_YEAR_FRAGMENT = "(?:yil|year\\w*|\u0433\u043e\u0434\\w*|\u043b\u0435\u0442|\u0433\\.?)"
_WARRANTY_MONTH_FRAGMENT = "(?:oy|month\\w*|\u043c\u0435\u0441\\w*|\u043c\u0435\u0441\u044f\u0446\\w*)"
_WARRANTY_YEAR_RE = re.compile(rf"(\d+)\s*{_WARRANTY_YEAR_FRAGMENT}", re.IGNORECASE)
_WARRANTY_MONTH_RE = re.compile(rf"(\d+)\s*{_WARRANTY_MONTH_FRAGMENT}", re.IGNORECASE)
_WARRANTY_COMPOSITE_RE = re.compile(
    rf"(?:\d+\s*(?:{_WARRANTY_YEAR_FRAGMENT}|{_WARRANTY_MONTH_FRAGMENT})\s*(?:[-/+])\s*\d+(?:\s*(?:{_WARRANTY_YEAR_FRAGMENT}|{_WARRANTY_MONTH_FRAGMENT}))?"
    rf"|\d+\s*(?:[-/+])\s*\d+\s*(?:{_WARRANTY_YEAR_FRAGMENT}|{_WARRANTY_MONTH_FRAGMENT}))",
    re.IGNORECASE,
)
_WARRANTY_AMBIGUOUS_RE = re.compile(
    "(?:\\bup\\s*to\\b|\\bmax(?:imum)?\\b|\\bдо\\b|\\bне\\s*более\\b|\\bмакс(?:имум)?\\b)",
    re.IGNORECASE,
)


def normalize_warranty_months(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if _WARRANTY_AMBIGUOUS_RE.search(raw) or _WARRANTY_COMPOSITE_RE.search(raw):
        return None

    year_matches = list(_WARRANTY_YEAR_RE.finditer(raw))
    month_matches = list(_WARRANTY_MONTH_RE.finditer(raw))
    if len(year_matches) + len(month_matches) > 1:
        return None
    if len(year_matches) == 1:
        return int(year_matches[0].group(1)) * 12
    if len(month_matches) == 1:
        return int(month_matches[0].group(1))

    m = re.fullmatch(r"([1-9]\d{0,2})", raw)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 120:
            return val
    return None


# ---------------------------------------------------------------------------
# Resolution (string cleanup)
# ---------------------------------------------------------------------------


def normalize_resolution(raw: str | None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    cleaned = re.sub(r"\s*[×хXx]\s*", "x", raw)
    return cleaned


# ---------------------------------------------------------------------------
# Plausibility (typed partial layer — keep ranges conservative)
# ---------------------------------------------------------------------------


def is_plausible_ram_gb(value: int) -> bool:
    return 1 <= int(value) <= 128


def is_plausible_storage_gb(value: int) -> bool:
    return 1 <= int(value) <= 8192


def is_plausible_display_size(value: float) -> bool:
    return 1.0 <= float(value) <= 100.0


def is_plausible_battery_mah(value: int) -> bool:
    return 500 <= int(value) <= 20000


def is_plausible_weight_g(value: int) -> bool:
    return 50 <= int(value) <= 100_000


def is_plausible_weight_kg(value: float) -> bool:
    return 0.05 <= float(value) <= 80.0


# ---------------------------------------------------------------------------
# Generic int extraction
# ---------------------------------------------------------------------------


def normalize_int_field(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if re.search(r"\d+\.\d+", text) or re.search(r"\d+\s*[-–—/]\s*\d+", text):
        return None
    if re.fullmatch(r"[1-9]\d*", text):
        return int(text)
    m = re.fullmatch(r"(?:x\s*)?([1-9]\d*)(?:\s*x)?", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(
        r"\b([1-9]\d*)\s*(?:ports?|inputs?|slots?|pcs?|pieces?|шт|разъем\w*)\b",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    m = re.search(r"\bx\s*([1-9]\d*)\b|\b([1-9]\d*)\s*x\b", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1) or m.group(2))
    return None


# ---------------------------------------------------------------------------
# Field-value dispatch (shared by structured & regex extractors)
# ---------------------------------------------------------------------------

_BOOLEAN_FIELDS = frozenset({"nfc", "has_wifi", "has_bluetooth", "hdmi"})
_STRING_FIELDS = frozenset({
    "display_resolution", "display_type", "os", "gpu",
    "storage_type", "energy_class", "display_tech", "resolution",
})
_NEGATIVE_BOOL_VALUES = frozenset({
    "нет", "no", "false", "0", "-", "отсутствует", "йўқ", "yo'q",
})

_NORMALIZERS: dict[str, object] = {
    "ram_gb": normalize_ram,
    "storage_gb": normalize_storage,
    "battery_mah": normalize_battery,
    "display_size_inch": normalize_display,
    "processor": normalize_processor,
    "main_camera_mp": normalize_camera_mp,
    "front_camera_mp": normalize_camera_mp,
    "sim_count": normalize_sim_count,
    "weight_g": normalize_weight_g,
    "weight_kg": normalize_weight_kg,
    "color": normalize_color,
    "hdmi_count": normalize_int_field,
    "refresh_rate_hz": normalize_refresh_rate,
    "power_w": normalize_power_w,
    "volume_l": normalize_volume_l,
    "warranty_months": normalize_warranty_months,
    "battery_wh": normalize_battery_wh,
    "usb_c_count": normalize_int_field,
    "smart_tv": normalize_smart_tv,
}


def normalize_field_value(field_name: str, raw_value: str) -> object:
    if field_name in _BOOLEAN_FIELDS:
        result = normalize_bool(raw_value)
        return result if result is not None else _infer_boolean_feature(field_name, raw_value)

    if field_name in _STRING_FIELDS:
        v = raw_value.strip()
        return v if v else None

    fn = _NORMALIZERS.get(field_name)
    if fn:
        return fn(raw_value)

    v = raw_value.strip()
    return v if v else None
