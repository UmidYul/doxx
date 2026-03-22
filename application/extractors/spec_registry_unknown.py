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

UNKNOWN_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="unknown",
    enabled_fields=frozenset(_UNKNOWN_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_UNKNOWN_ORDER,
    extraction_priority_order=_UNKNOWN_ORDER,
)

ACCESSORY_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="accessory",
    enabled_fields=frozenset(_UNKNOWN_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_UNKNOWN_ORDER,
    extraction_priority_order=_UNKNOWN_ORDER,
)
