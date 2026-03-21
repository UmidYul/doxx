from __future__ import annotations

import logging

from flashtext import KeywordProcessor

from application.extractors.patterns import (
    LAPTOP_PATTERNS,
    PHONE_PATTERNS,
    TV_PATTERNS,
)
from application.extractors.unit_normalizer import normalize_field_value

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Keywords for fast pre-filtering via flashtext
# ═══════════════════════════════════════════════════════════════════════════

_FIELD_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "phone": {
        "ram_gb": [
            "RAM", "ОЗУ", "оперативная память", "оперативка",
            "operativ xotira", "ГБ ОЗУ", "GB RAM",
        ],
        "storage_gb": [
            "встроенная память", "ichki xotira", "ПЗУ", "ROM",
            "внутренняя память", "накопитель", "storage",
        ],
        "battery_mah": [
            "мАч", "mAh", "аккумулятор", "батарея", "batareya", "battery",
        ],
        "display_size_inch": [
            "дюйм", "inch", "диагональ", "ekran", "display",
        ],
        "processor": [
            "процессор", "Snapdragon", "Dimensity", "Exynos",
            "Bionic", "Helio", "Kirin", "chipset", "protsessor",
        ],
        "main_camera_mp": [
            "основная камера", "asosiy kamera", "rear camera",
            "задняя камера", "Мп", "MP", "мегапиксел",
        ],
        "front_camera_mp": [
            "фронтальная камера", "old kamera", "front camera",
            "передняя камера", "селфи", "selfie",
        ],
        "display_type": [
            "AMOLED", "IPS", "OLED", "Super AMOLED", "TFT", "Retina",
        ],
        "os": [
            "Android", "iOS", "HarmonyOS", "операционная система",
            "operatsion tizim",
        ],
        "nfc": ["NFC"],
        "sim_count": ["SIM", "Dual SIM", "nano-SIM", "нано-SIM"],
        "weight_g": ["грамм", "gram", "вес", "масса", "weight"],
    },
    "laptop": {
        "ram_gb": [
            "RAM", "ОЗУ", "DDR", "LPDDR", "оперативная", "operativ",
        ],
        "storage_gb": [
            "SSD", "HDD", "NVMe", "накопитель", "storage", "ichki xotira",
        ],
        "processor": [
            "процессор", "Intel", "AMD", "Core i", "Ryzen", "Apple M",
        ],
        "display_size_inch": [
            "дюйм", "inch", "диагональ", "ekran", "display",
        ],
        "gpu": [
            "видеокарта", "GeForce", "RTX", "GTX", "Radeon",
            "GPU", "графика", "Intel Iris", "Intel UHD", "Intel Arc",
        ],
        "os": [
            "Windows", "macOS", "Ubuntu", "Linux", "ChromeOS", "FreeDOS",
        ],
        "storage_type": ["SSD", "HDD", "NVMe", "eMMC"],
        "battery_wh": ["Вт·ч", "Wh", "Втч", "watt-hour"],
        "weight_kg": ["кг", "kg", "вес", "масса", "weight"],
        "usb_c_count": ["USB-C", "USB Type-C", "Type-C", "USB C"],
    },
    "tv": {
        "display_size_inch": [
            "дюйм", "inch", "диагональ", "ekran", "display",
        ],
        "resolution": [
            "4K", "Full HD", "8K", "UHD", "HD",
            "разрешение", "3840", "1920", "7680",
        ],
        "display_tech": [
            "QLED", "OLED", "LED", "Mini LED", "Neo QLED", "Nano Cell",
        ],
        "refresh_rate_hz": [
            "Гц", "Hz", "герц", "частота обновления",
        ],
        "smart_tv": [
            "Smart TV", "Android TV", "Tizen", "webOS",
            "Google TV", "Vidaa",
        ],
        "has_wifi": ["Wi-Fi", "WiFi", "802.11", "вай-фай"],
        "hdmi_count": ["HDMI"],
    },
}

_EXCLUDED_META = frozenset({"extraction_method", "completeness_score", "raw_fields"})


class RegexExtractor:
    """Enrich partially-filled specs by scanning description text with regex."""

    def __init__(self) -> None:
        self.keyword_processors: dict[str, KeywordProcessor] = {}
        self._build_processors()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_processors(self) -> None:
        for category, fields in _FIELD_KEYWORDS.items():
            proc = KeywordProcessor(case_sensitive=False)
            for field_name, keywords in fields.items():
                for kw in keywords:
                    proc.add_keyword(kw, field_name)
            self.keyword_processors[category] = proc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, specs: object, text: str, category: str = "phone") -> object:
        patterns = self._get_patterns(category)
        if not patterns:
            return specs

        schema_fields = set(specs.model_fields.keys()) - _EXCLUDED_META  # type: ignore[attr-defined]

        processor = self.keyword_processors.get(category)
        candidate_fields: set[str] = (
            set(processor.extract_keywords(text)) if processor else set(patterns.keys())
        )

        for field in candidate_fields:
            if field not in patterns or field not in schema_fields:
                continue
            if getattr(specs, field, None) is not None:
                continue
            self._try_extract(specs, field, patterns[field], text)

        for field in patterns:
            if field not in schema_fields:
                continue
            if getattr(specs, field, None) is not None:
                continue
            if field in candidate_fields:
                continue
            self._try_extract(specs, field, patterns[field], text)

        if specs.extraction_method == "unknown":  # type: ignore[attr-defined]
            specs.extraction_method = "regex"  # type: ignore[attr-defined]
        specs.compute_score()  # type: ignore[attr-defined]
        return specs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _try_extract(
        specs: object,
        field: str,
        patterns: list,
        text: str,
    ) -> None:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                raw_value = (match.groupdict().get("value") or match.group(0)).strip()
                normalized = normalize_field_value(field, raw_value)
                if normalized is not None:
                    setattr(specs, field, normalized)
                    return

    @staticmethod
    def _get_patterns(category: str) -> dict:
        mapping = {
            "phone": PHONE_PATTERNS,
            "laptop": LAPTOP_PATTERNS,
            "tv": TV_PATTERNS,
        }
        return mapping.get(category, PHONE_PATTERNS)
