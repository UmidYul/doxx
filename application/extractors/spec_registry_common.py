from __future__ import annotations

from application.extractors.spec_registry import SpecAliasRule, SpecFieldDefinition

_ALL_CATS = frozenset(
    {"phone", "tablet", "laptop", "tv", "appliance", "accessory", "unknown"}
)

# (field_name, value_type, normalizer_name, plausibility_checker|None)
_FIELD_META: tuple[tuple[str, str, str, str | None], ...] = (
    ("ram_gb", "int", "ram_gb", "is_plausible_ram_gb"),
    ("storage_gb", "int", "storage_gb", "is_plausible_storage_gb"),
    ("display_size_inch", "float", "display_size_inch", "is_plausible_display_size"),
    ("display_resolution", "str", "display_resolution", None),
    ("display_type", "str", "display_type", None),
    ("display_tech", "str", "display_tech", None),
    ("refresh_rate_hz", "int", "refresh_rate_hz", None),
    ("processor", "str", "processor", None),
    ("gpu", "str", "gpu", None),
    ("battery_mah", "int", "battery_mah", "is_plausible_battery_mah"),
    ("battery_wh", "float", "battery_wh", None),
    ("weight_g", "int", "weight_g", "is_plausible_weight_g"),
    ("weight_kg", "float", "weight_kg", "is_plausible_weight_kg"),
    ("color", "str", "color", None),
    ("sim_count", "int", "sim_count", None),
    ("main_camera_mp", "int", "main_camera_mp", None),
    ("front_camera_mp", "int", "front_camera_mp", None),
    ("volume_l", "float", "volume_l", None),
    ("power_w", "int", "power_w", None),
    ("smart_tv", "bool", "smart_tv", None),
    ("has_wifi", "bool", "has_wifi", None),
    ("has_bluetooth", "bool", "has_bluetooth", None),
    ("hdmi", "bool", "hdmi", None),
    ("hdmi_count", "int", "hdmi_count", None),
    ("usb_c_count", "int", "usb_c_count", None),
    ("os", "str", "os", None),
    ("energy_class", "str", "energy_class", None),
    ("warranty_months", "int", "warranty_months", None),
)


def build_common_field_definitions() -> dict[str, SpecFieldDefinition]:
    out: dict[str, SpecFieldDefinition] = {}
    for fn, vt, nn, pl in _FIELD_META:
        out[fn] = SpecFieldDefinition(
            field_name=fn,
            value_type=vt,  # type: ignore[arg-type]
            supported_categories=_ALL_CATS,
            normalizer_name=nn,
            plausibility_checker=pl,
            priority=0,
            synonyms=(),
        )
    return out


# Common alias rules (human-readable labels; loader normalizes keys).
def _ar(
    raw: str,
    typed: str,
    *,
    pri: int = 0,
    dep: bool = False,
) -> SpecAliasRule:
    return SpecAliasRule(
        raw_label=raw,
        canonical_label=raw,
        typed_field=typed,
        category_scope=None,
        store_scope=None,
        priority=pri,
        is_deprecated=dep,
    )


COMMON_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    _ar("оперативная память", "ram_gb"),
    _ar("озу", "ram_gb"),
    _ar("ram", "ram_gb"),
    _ar("встроенная память", "storage_gb"),
    _ar("внутренняя память", "storage_gb"),
    _ar("память", "storage_gb"),
    _ar("хранилище", "storage_gb"),
    _ar("storage", "storage_gb"),
    _ar("частота развертки экрана", "refresh_rate_hz"),
    _ar("частота обновления", "refresh_rate_hz"),
    _ar("refresh rate", "refresh_rate_hz"),
    _ar("диагональ экрана", "display_size_inch"),
    _ar("диагональ", "display_size_inch"),
    _ar("разрешение экрана", "display_resolution"),
    _ar("разрешение", "display_resolution"),
    _ar("\u0440\u0430\u0437\u043c\u0435\u0440 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f", "display_resolution"),
    _ar("тип экрана", "display_type"),
    _ar("\u0442\u0438\u043f \u0434\u0438\u0441\u043f\u043b\u0435\u044f", "display_type"),
    _ar("\u0442\u0438\u043f \u043c\u0430\u0442\u0440\u0438\u0446\u044b \u044d\u043a\u0440\u0430\u043d\u0430", "display_type"),
    _ar("технология экрана", "display_tech"),
    _ar("процессор", "processor"),
    _ar("модель процессора", "processor"),
    _ar("видеопроцессор", "gpu"),
    _ar("видеокарта", "gpu"),
    _ar("gpu", "gpu"),
    _ar("емкость аккумулятора", "battery_mah"),
    _ar("ёмкость аккумулятора", "battery_mah"),
    _ar("аккумулятор", "battery_mah"),
    _ar("battery", "battery_mah"),
    _ar("батарея wh", "battery_wh"),
    _ar("батарея, wh", "battery_wh"),
    _ar("емкость батареи", "battery_wh"),
    _ar("вес", "weight_g"),
    _ar("масса", "weight_kg"),
    _ar("цвет", "color"),
    _ar("количество sim-карт", "sim_count"),
    _ar("количество sim карт", "sim_count"),
    _ar("sim", "sim_count"),
    _ar("основная камера", "main_camera_mp"),
    _ar("фронтальная камера", "front_camera_mp"),
    _ar("общий объем", "volume_l"),
    _ar("общий объём", "volume_l"),
    _ar("объем", "volume_l"),
    _ar("объём", "volume_l"),
    _ar("потребляемая мощность", "power_w"),
    _ar("мощность", "power_w"),
    _ar("smart tv", "smart_tv"),
    _ar("\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 smart tv", "smart_tv"),
    _ar("wi-fi", "has_wifi"),
    _ar("wifi", "has_wifi"),
    _ar("bluetooth", "has_bluetooth"),
    _ar("\u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442 bluetooth", "has_bluetooth"),
    _ar("\u0432\u0435\u0440\u0441\u0438\u044f bluetooth", "has_bluetooth"),
    _ar("hdmi", "hdmi"),
    _ar("количество hdmi", "hdmi_count"),
    _ar("usb-c", "usb_c_count"),
    _ar("usb c", "usb_c_count"),
    _ar("операционная система", "os"),
    _ar("ос", "os"),
    _ar("\u0432\u0435\u0440\u0441\u0438\u044f \u043e\u0441 \u043d\u0430 \u043d\u0430\u0447\u0430\u043b\u043e \u043f\u0440\u043e\u0434\u0430\u0436", "os"),
    _ar("класс энергопотребления", "energy_class"),
    _ar("энергокласс", "energy_class"),
    _ar("гарантия", "warranty_months"),
    # Informal / legacy label (tests + governance warnings)
    _ar("оперативка", "ram_gb", pri=-5, dep=True),
)

FIELD_DEFINITIONS: dict[str, SpecFieldDefinition] = build_common_field_definitions()
