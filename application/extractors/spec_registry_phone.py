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
    "sim_count",
    "processor",
    "weight_g",
    "color",
    "os",
)

PHONE_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="phone",
    enabled_fields=frozenset(_PHONE_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_PHONE_ORDER,
    extraction_priority_order=_PHONE_ORDER,
)

CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = ()
