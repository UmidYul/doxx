from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy

_UNKNOWN_ORDER: tuple[str, ...] = (
    "ram_gb",
    "storage_gb",
    "display_size_inch",
    "battery_mah",
    "processor",
    "color",
    "os",
)

_ACCESSORY_ORDER: tuple[str, ...] = (
    "display_size_inch",
    "display_resolution",
    "display_type",
    "display_tech",
    "refresh_rate_hz",
    "battery_mah",
    "battery_wh",
    "weight_g",
    "weight_kg",
    "color",
    "power_w",
    "has_wifi",
    "has_bluetooth",
    "hdmi",
    "hdmi_count",
    "usb_c_count",
    "os",
    "warranty_months",
)

UNKNOWN_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="unknown",
    enabled_fields=frozenset(_UNKNOWN_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_UNKNOWN_ORDER,
    extraction_priority_order=_UNKNOWN_ORDER,
)

ACCESSORY_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="accessory",
    enabled_fields=frozenset(_ACCESSORY_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_ACCESSORY_ORDER,
    extraction_priority_order=_ACCESSORY_ORDER,
)
