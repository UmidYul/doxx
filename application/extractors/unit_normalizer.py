from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

logger = logging.getLogger(__name__)

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

_STORAGE_RE = re.compile(
    r"(\d+)\s*(TB|ТБ|tb|тб|GB|ГБ|Гб|гб|gb)", re.IGNORECASE
)


def normalize_storage(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _STORAGE_RE.search(raw)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        if unit in ("tb", "тб"):
            return val * 1024
        return val
    digits = re.findall(r"\d+", raw)
    if digits:
        return int(digits[0])
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

_CM_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*(?:см|cm)", re.IGNORECASE)
_INCH_PATTERN = re.compile(
    r"""(\d+[.,]?\d*)\s*(?:дюйм\w*|inch\w*|"|″|'')""", re.IGNORECASE
)
_PLAIN_DISPLAY = re.compile(r"(\d+(?:[.,]\d+)?)")


def normalize_display(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    m = _CM_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        val = round(val / 2.54, 1)
        if 1.0 <= val <= 100.0:
            return val
        return None

    m = _INCH_PATTERN.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        if 1.0 <= val <= 100.0:
            return val
        return None

    m = _PLAIN_DISPLAY.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        if 1.0 <= val <= 100.0:
            return val
    return None


# ---------------------------------------------------------------------------
# Battery (phone, mAh)
# ---------------------------------------------------------------------------

_BATTERY_RE = re.compile(
    r"(\d{3,5})\s*(?:мАч|mAh|мач|mah)", re.IGNORECASE
)
_BATTERY_PLAIN = re.compile(r"(\d{3,5})")


def normalize_battery(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    m = _BATTERY_RE.search(raw)
    if m:
        val = int(m.group(1))
        if 500 <= val <= 20000:
            return val
        return None

    m = _BATTERY_PLAIN.search(raw)
    if m:
        val = int(m.group(1))
        if 500 <= val <= 20000:
            return val
    return None


# ---------------------------------------------------------------------------
# Battery (laptop, Wh)
# ---------------------------------------------------------------------------

_BATTERY_WH_RE = re.compile(
    r"(\d+[.,]?\d*)\s*(?:Вт\s*[·*⋅]?\s*ч|Wh|wh|Втч)", re.IGNORECASE
)


def normalize_battery_wh(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _BATTERY_WH_RE.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
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

_CAMERA_RE = re.compile(
    r"(\d+)\s*(?:Мп|MP|Mp|мп|мегапиксел\w*|megapixel\w*)", re.IGNORECASE
)


def normalize_camera_mp(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _CAMERA_RE.search(raw)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 200:
            return val
        return None
    m = re.search(r"(\d+)", raw)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 200:
            return val
    return None


# ---------------------------------------------------------------------------
# SIM count
# ---------------------------------------------------------------------------


def normalize_sim_count(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip().lower()
    if not raw:
        return None
    if any(kw in raw for kw in ("dual", "ikki", "два", "2", "duos")):
        return 2
    if any(kw in raw for kw in ("single", "один", "bitta", "1")):
        return 1
    m = re.search(r"(\d)", raw)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 4:
            return val
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


def normalize_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    raw = raw.strip().lower()
    if not raw:
        return None
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    for v in _TRUE_VALUES:
        if v in raw:
            return True
    for v in _FALSE_VALUES:
        if v in raw:
            return False
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

_HZ_RE = re.compile(r"(\d+)\s*(?:Гц|Hz|гц|hz|герц)", re.IGNORECASE)

_KNOWN_RATES = frozenset({24, 30, 50, 60, 75, 90, 120, 144, 165, 240})


def normalize_refresh_rate(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _HZ_RE.search(raw)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", raw)
    if m:
        val = int(m.group(1))
        if val in _KNOWN_RATES:
            return val
    return None


# ---------------------------------------------------------------------------
# Power (W)
# ---------------------------------------------------------------------------

_POWER_RE = re.compile(r"(\d+)\s*(?:Вт|W|вт|w)\b", re.IGNORECASE)


def normalize_power_w(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _POWER_RE.search(raw)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", raw)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Volume (litres)
# ---------------------------------------------------------------------------

_VOLUME_RE = re.compile(
    r"(\d+[.,]?\d*)\s*(?:л(?!с)|l(?!b)|литр\w*|litr\w*)\b", re.IGNORECASE
)


def normalize_volume_l(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _VOLUME_RE.search(raw)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+[.,]?\d*)", raw)
    if m:
        return float(m.group(1).replace(",", "."))
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

_WARRANTY_YEAR_RE = re.compile(
    r"(\d+)\s*(?:год\w*|yil|year\w*|лет|г\.?)", re.IGNORECASE
)
_WARRANTY_MONTH_RE = re.compile(
    r"(\d+)\s*(?:мес\w*|oy|month\w*|месяц\w*)", re.IGNORECASE
)


def normalize_warranty_months(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _WARRANTY_YEAR_RE.search(raw)
    if m:
        return int(m.group(1)) * 12
    m = _WARRANTY_MONTH_RE.search(raw)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", raw)
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
    raw = raw.strip()
    if not raw:
        return None
    m = re.search(r"(\d+)", raw)
    if m:
        return int(m.group(1))
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
        if result is None and raw_value.strip():
            if raw_value.strip().lower() not in _NEGATIVE_BOOL_VALUES:
                return True
        return result

    if field_name in _STRING_FIELDS:
        v = raw_value.strip()
        return v if v else None

    fn = _NORMALIZERS.get(field_name)
    if fn:
        return fn(raw_value)

    v = raw_value.strip()
    return v if v else None
