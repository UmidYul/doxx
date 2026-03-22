from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy, SpecAliasRule

_APPLIANCE_ORDER: tuple[str, ...] = (
    "volume_l",
    "power_w",
    "energy_class",
    "warranty_months",
    "weight_kg",
    "color",
)

APPLIANCE_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="appliance",
    enabled_fields=frozenset(_APPLIANCE_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_APPLIANCE_ORDER,
    extraction_priority_order=_APPLIANCE_ORDER,
)

CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    SpecAliasRule(
        raw_label="объем камеры",
        canonical_label="объем камеры",
        typed_field="volume_l",
        category_scope="appliance",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="полезный объем",
        canonical_label="полезный объем",
        typed_field="volume_l",
        category_scope="appliance",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="класс энергопотребления",
        canonical_label="класс энергопотребления",
        typed_field="energy_class",
        category_scope="appliance",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
)
