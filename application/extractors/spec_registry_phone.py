from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy, SpecAliasRule

_PHONE_ORDER: tuple[str, ...] = (
    "ram_gb",
    "storage_gb",
    "battery_mah",
    "main_camera_mp",
    "front_camera_mp",
    "display_size_inch",
    "display_resolution",
    "display_type",
    "refresh_rate_hz",
    "sim_count",
    "processor",
    "weight_g",
    "color",
    "os",
    "has_wifi",
    "has_bluetooth",
)

PHONE_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="phone",
    enabled_fields=frozenset(_PHONE_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_PHONE_ORDER,
    extraction_priority_order=_PHONE_ORDER,
)


def _ar(raw: str, typed: str, *, pri: int = 0) -> SpecAliasRule:
    return SpecAliasRule(
        raw_label=raw,
        canonical_label=raw,
        typed_field=typed,
        category_scope="phone",
        store_scope=None,
        priority=pri,
    )


CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    # RAM aliases specific to phone listings on UZ stores
    _ar("объем оперативной памяти", "ram_gb"),
    _ar("объём оперативной памяти", "ram_gb"),
    _ar("оперативная память (ram)", "ram_gb"),
    _ar("ram (гб)", "ram_gb"),
    _ar("объём озу", "ram_gb"),
    # Storage
    _ar("объем встроенной памяти", "storage_gb"),
    _ar("объём встроенной памяти", "storage_gb"),
    _ar("пзу", "storage_gb"),
    _ar("rom", "storage_gb"),
    _ar("rom (гб)", "storage_gb"),
    _ar("объём пзу", "storage_gb"),
    # Battery
    _ar("ёмкость батареи", "battery_mah"),
    _ar("емкость батареи", "battery_mah"),
    _ar("батарея (мач)", "battery_mah"),
    _ar("battery capacity", "battery_mah"),
    # Camera
    _ar("камера", "main_camera_mp"),
    _ar("задняя камера", "main_camera_mp"),
    _ar("основная (тыловая) камера", "main_camera_mp"),
    _ar("тыловая камера", "main_camera_mp"),
    _ar("rear camera", "main_camera_mp"),
    _ar("main camera", "main_camera_mp"),
    _ar("селфи камера", "front_camera_mp"),
    _ar("передняя камера", "front_camera_mp"),
    _ar("selfie camera", "front_camera_mp"),
    _ar("front camera", "front_camera_mp"),
    # Display
    _ar("размер экрана", "display_size_inch"),
    _ar("размер дисплея", "display_size_inch"),
    _ar("экран", "display_size_inch"),
    _ar("screen size", "display_size_inch"),
    _ar("тип дисплея", "display_type"),
    _ar("тип матрицы", "display_type"),
    _ar("display type", "display_type"),
    _ar("частота обновления экрана", "refresh_rate_hz"),
    # SIM
    _ar("sim-карта", "sim_count"),
    _ar("sim карта", "sim_count"),
    _ar("тип sim-карты", "sim_count"),
    _ar("тип sim карты", "sim_count"),
    _ar("dual sim", "sim_count"),
    _ar("nano-sim", "sim_count"),
    # Connectivity
    _ar("nfc", "has_bluetooth"),  # NFC presence often in bluetooth-like field
    _ar("wi-fi", "has_wifi"),
    _ar("bluetooth", "has_bluetooth"),
    _ar("стандарт wi-fi", "has_wifi"),
    _ar("версия bluetooth", "has_bluetooth"),
    _ar("беспроводные интерфейсы", "has_wifi"),
    # Processor
    _ar("чипсет", "processor"),
    _ar("chipset", "processor"),
    _ar("soc", "processor"),
    _ar("частота процессора", "processor"),
    # OS
    _ar("версия ос", "os"),
    _ar("android version", "os"),
    # Weight
    _ar("масса", "weight_g"),
    _ar("масса, г", "weight_g"),
    _ar("вес, г", "weight_g"),
    # Color
    _ar("цвет корпуса", "color"),
    _ar("цвет товара", "color"),
    _ar("расцветка", "color"),
)
