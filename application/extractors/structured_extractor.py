from __future__ import annotations

import logging
from difflib import SequenceMatcher

from application.extractors.unit_normalizer import normalize_field_value

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 130+ label aliases: RU / UZ / EN  →  schema field name
# Keys MUST be lowercase (the extractor lowercases every incoming label).
# ═══════════════════════════════════════════════════════════════════════════

FIELD_ALIASES: dict[str, str] = {
    # --- RAM (ram_gb) ---
    "оперативная память": "ram_gb",
    "оперативн. память": "ram_gb",
    "оперативка": "ram_gb",
    "озу": "ram_gb",
    "ram": "ram_gb",
    "ozu": "ram_gb",
    "operativ xotira": "ram_gb",
    "объём озу": "ram_gb",
    "объем озу": "ram_gb",
    "оперативная": "ram_gb",
    "ram memory": "ram_gb",

    # --- Storage (storage_gb) ---
    "встроенная память": "storage_gb",
    "внутренняя память": "storage_gb",
    "ichki xotira": "storage_gb",
    "storage": "storage_gb",
    "пзу": "storage_gb",
    "rom": "storage_gb",
    "объём памяти": "storage_gb",
    "объем памяти": "storage_gb",
    "накопитель": "storage_gb",
    "внутреннее хранилище": "storage_gb",
    "ёмкость памяти": "storage_gb",
    "емкость памяти": "storage_gb",
    "flash memory": "storage_gb",
    "xotira hajmi": "storage_gb",

    # --- Battery phone (battery_mah) ---
    "ёмкость аккумулятора": "battery_mah",
    "емкость аккумулятора": "battery_mah",
    "аккумулятор": "battery_mah",
    "батарея": "battery_mah",
    "batareya sig'imi": "battery_mah",
    "batareya sig\u2019imi": "battery_mah",
    "batareya": "battery_mah",
    "battery": "battery_mah",
    "battery capacity": "battery_mah",
    "akkumulyator": "battery_mah",

    # --- Display size (display_size_inch) ---
    "экран": "display_size_inch",
    "диагональ экрана": "display_size_inch",
    "диагональ": "display_size_inch",
    "размер экрана": "display_size_inch",
    "ekran o'lchami": "display_size_inch",
    "ekran o\u2019lchami": "display_size_inch",
    "ekran": "display_size_inch",
    "screen size": "display_size_inch",
    "display": "display_size_inch",
    "display size": "display_size_inch",
    "размер дисплея": "display_size_inch",

    # --- Display type (display_type / display_tech) ---
    "тип экрана": "display_type",
    "тип дисплея": "display_type",
    "тип матрицы": "display_type",
    "ekran turi": "display_type",
    "display type": "display_type",
    "matritsa turi": "display_type",
    "screen type": "display_type",
    "технология экрана": "display_tech",
    "технология дисплея": "display_tech",
    "тип подсветки": "display_tech",
    "panel type": "display_tech",
    "ekran texnologiyasi": "display_tech",

    # --- Display resolution (display_resolution / resolution) ---
    "разрешение экрана": "display_resolution",
    "разрешение": "display_resolution",
    "разрешение дисплея": "display_resolution",
    "ekran ruxsati": "display_resolution",
    "screen resolution": "display_resolution",
    "display resolution": "display_resolution",
    "разрешение (пиксели)": "resolution",

    # --- Processor ---
    "процессор": "processor",
    "protsessor": "processor",
    "chipset": "processor",
    "cpu": "processor",
    "чипсет": "processor",
    "чип": "processor",
    "protsessor modeli": "processor",
    "модель процессора": "processor",

    # --- Main camera ---
    "основная камера": "main_camera_mp",
    "asosiy kamera": "main_camera_mp",
    "rear camera": "main_camera_mp",
    "задняя камера": "main_camera_mp",
    "back camera": "main_camera_mp",
    "orqa kamera": "main_camera_mp",
    "главная камера": "main_camera_mp",
    "основная": "main_camera_mp",
    "камера": "main_camera_mp",

    # --- Front camera ---
    "фронтальная камера": "front_camera_mp",
    "old kamera": "front_camera_mp",
    "front camera": "front_camera_mp",
    "передняя камера": "front_camera_mp",
    "селфи камера": "front_camera_mp",
    "oldingi kamera": "front_camera_mp",
    "selfie camera": "front_camera_mp",
    "фронтальная": "front_camera_mp",

    # --- OS ---
    "операционная система": "os",
    "operatsion tizim": "os",
    "ос": "os",
    "operating system": "os",
    "операционка": "os",
    "ot": "os",

    # --- SIM count ---
    "количество sim": "sim_count",
    "количество sim-карт": "sim_count",
    "sim kartalar soni": "sim_count",
    "sim": "sim_count",
    "sim-карта": "sim_count",
    "число sim-карт": "sim_count",
    "sim cards": "sim_count",

    # --- NFC ---
    "nfc": "nfc",
    "модуль nfc": "nfc",

    # --- Weight (phone → weight_g, laptop/appliance → weight_kg) ---
    "вес": "weight_g",
    "og'irligi": "weight_g",
    "og\u2019irligi": "weight_g",
    "weight": "weight_g",
    "масса": "weight_g",
    "вес устройства": "weight_g",
    "og'irlik": "weight_g",

    # --- Color ---
    "цвет": "color",
    "rang": "color",
    "color": "color",
    "расцветка": "color",
    "цвет корпуса": "color",
    "rangi": "color",

    # --- GPU ---
    "видеокарта": "gpu",
    "gpu": "gpu",
    "graphics": "gpu",
    "графический процессор": "gpu",
    "графика": "gpu",
    "grafik karta": "gpu",
    "видеочип": "gpu",
    "graphics card": "gpu",

    # --- Storage type ---
    "тип накопителя": "storage_type",
    "xotira turi": "storage_type",
    "storage type": "storage_type",
    "тип хранилища": "storage_type",
    "тип диска": "storage_type",

    # --- HDMI ---
    "hdmi": "hdmi_count",
    "порты hdmi": "hdmi_count",
    "количество hdmi": "hdmi_count",
    "hdmi ports": "hdmi_count",

    # --- Refresh rate ---
    "частота обновления": "refresh_rate_hz",
    "yangilanish chastotasi": "refresh_rate_hz",
    "refresh rate": "refresh_rate_hz",
    "герцовка": "refresh_rate_hz",
    "частота обновления экрана": "refresh_rate_hz",

    # --- Wi-Fi ---
    "wi-fi": "has_wifi",
    "wifi": "has_wifi",
    "вай-фай": "has_wifi",
    "беспроводная связь": "has_wifi",
    "wi-fi модуль": "has_wifi",

    # --- Bluetooth ---
    "bluetooth": "has_bluetooth",
    "блютуз": "has_bluetooth",
    "блютус": "has_bluetooth",
    "bluetooth версия": "has_bluetooth",

    # --- Smart TV ---
    "smart tv": "smart_tv",
    "смарт тв": "smart_tv",
    "смарт-тв": "smart_tv",
    "платформа smart tv": "smart_tv",

    # --- Power ---
    "мощность": "power_w",
    "quvvat": "power_w",
    "power": "power_w",
    "потребляемая мощность": "power_w",
    "quvvati": "power_w",
    "номинальная мощность": "power_w",

    # --- Volume ---
    "объём": "volume_l",
    "объем": "volume_l",
    "hajm": "volume_l",
    "volume": "volume_l",
    "вместимость": "volume_l",
    "ёмкость": "volume_l",
    "емкость": "volume_l",
    "sig'im": "volume_l",

    # --- Energy class ---
    "класс энергопотребления": "energy_class",
    "энергокласс": "energy_class",
    "energy class": "energy_class",
    "energiya sinfi": "energy_class",
    "класс энергоэффективности": "energy_class",

    # --- Warranty ---
    "гарантия": "warranty_months",
    "kafolat": "warranty_months",
    "warranty": "warranty_months",
    "срок гарантии": "warranty_months",
    "гарантийный срок": "warranty_months",
    "kafolat muddati": "warranty_months",

    # --- Battery Wh (laptop) ---
    "ёмкость батареи": "battery_wh",
    "емкость батареи": "battery_wh",
    "battery capacity wh": "battery_wh",
    "аккумулятор (вт·ч)": "battery_wh",

    # --- USB-C count ---
    "usb type-c": "usb_c_count",
    "usb-c": "usb_c_count",
    "порты usb-c": "usb_c_count",
    "usb c": "usb_c_count",
}

# When a resolved field is missing from the target schema, try the related
# field before falling back to _unknown_fields.
FIELD_RELATED: dict[str, str] = {
    "weight_g": "weight_kg",
    "weight_kg": "weight_g",
    "hdmi_count": "hdmi",
    "hdmi": "hdmi_count",
    "battery_mah": "battery_wh",
    "battery_wh": "battery_mah",
    "display_resolution": "resolution",
    "resolution": "display_resolution",
    "display_type": "display_tech",
    "display_tech": "display_type",
}

_EXCLUDED_META = frozenset({"extraction_method", "completeness_score", "raw_fields"})
_FUZZY_THRESHOLD = 0.82


class StructuredExtractor:
    """Extract specs from key-value tables scraped from store pages."""

    def extract(self, raw_specs: dict, schema_class: type) -> object:
        from domain.specs.base import BaseSpecs

        specs: BaseSpecs = schema_class()
        schema_fields = set(specs.model_fields.keys()) - _EXCLUDED_META

        for label, value in raw_specs.items():
            normalized_label = self._normalize_label(label)
            field_name = FIELD_ALIASES.get(normalized_label)

            if not field_name:
                field_name = self._fuzzy_match(normalized_label)

            if field_name and field_name not in schema_fields:
                alt = FIELD_RELATED.get(field_name)
                if alt and alt in schema_fields:
                    field_name = alt
                else:
                    field_name = None

            if field_name and field_name in schema_fields:
                normalized_value = normalize_field_value(field_name, str(value))

                if (
                    field_name == "ram_gb"
                    and schema_class.__name__ == "PhoneSpecs"
                    and normalized_value is not None
                    and normalized_value > 32
                ):
                    logger.warning(
                        "[SPEC_SANITY_SWAP] RAM %s looks like storage for %s",
                        normalized_value,
                        label,
                    )
                    field_name = "storage_gb"

                if normalized_value is not None:
                    setattr(specs, field_name, normalized_value)
            else:
                specs.raw_fields.setdefault("_unknown_fields", {})[label] = value
                logger.debug("Unknown spec label: %s = %s", label, value)

        specs.extraction_method = "structured"
        specs.compute_score()
        return specs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_label(label: str) -> str:
        import re

        text = label.lower().strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _fuzzy_match(normalized_label: str) -> str | None:
        best_match: str | None = None
        best_ratio = 0.0
        for alias in FIELD_ALIASES:
            ratio = SequenceMatcher(None, normalized_label, alias).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = alias
        if best_ratio >= _FUZZY_THRESHOLD and best_match is not None:
            field = FIELD_ALIASES[best_match]
            logger.info(
                "[FUZZY_MATCH] '%s' → '%s' (%.2f)",
                normalized_label,
                best_match,
                best_ratio,
            )
            return field
        return None
