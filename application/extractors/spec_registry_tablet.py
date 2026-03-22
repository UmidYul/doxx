from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy, SpecAliasRule

_TABLET_ORDER: tuple[str, ...] = (
    "ram_gb",
    "storage_gb",
    "battery_mah",
    "display_size_inch",
    "display_resolution",
    "main_camera_mp",
    "front_camera_mp",
    "weight_g",
    "sim_count",
    "processor",
    "os",
)

TABLET_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="tablet",
    enabled_fields=frozenset(_TABLET_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_TABLET_ORDER,
    extraction_priority_order=_TABLET_ORDER,
)

CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    SpecAliasRule(
        raw_label="оперативная память",
        canonical_label="оперативная память",
        typed_field="ram_gb",
        category_scope="tablet",
        store_scope=None,
        priority=5,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="встроенная память",
        canonical_label="встроенная память",
        typed_field="storage_gb",
        category_scope="tablet",
        store_scope=None,
        priority=5,
        is_deprecated=False,
    ),
)
