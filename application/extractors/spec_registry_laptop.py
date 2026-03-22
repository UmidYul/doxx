from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy, SpecAliasRule

_LAPTOP_ORDER: tuple[str, ...] = (
    "ram_gb",
    "storage_gb",
    "processor",
    "gpu",
    "display_size_inch",
    "display_resolution",
    "battery_wh",
    "weight_kg",
    "weight_g",
    "os",
    "color",
)

LAPTOP_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="laptop",
    enabled_fields=frozenset(_LAPTOP_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_LAPTOP_ORDER,
    extraction_priority_order=_LAPTOP_ORDER,
)

CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    SpecAliasRule(
        raw_label="масса",
        canonical_label="масса",
        typed_field="weight_kg",
        category_scope="laptop",
        store_scope=None,
        priority=20,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="вес",
        canonical_label="вес",
        typed_field="weight_kg",
        category_scope="laptop",
        store_scope=None,
        priority=20,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="аккумулятор ноутбука",
        canonical_label="аккумулятор ноутбука",
        typed_field="battery_wh",
        category_scope="laptop",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
)
