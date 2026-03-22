from __future__ import annotations

from application.extractors.spec_registry import CategorySpecPolicy, SpecAliasRule

_TV_ORDER: tuple[str, ...] = (
    "display_size_inch",
    "display_resolution",
    "display_type",
    "display_tech",
    "smart_tv",
    "hdmi",
    "hdmi_count",
    "refresh_rate_hz",
    "power_w",
)

TV_CATEGORY_POLICY = CategorySpecPolicy(
    category_hint="tv",
    enabled_fields=frozenset(_TV_ORDER),
    preferred_aliases=(),
    conflict_resolution_order=_TV_ORDER,
    extraction_priority_order=_TV_ORDER,
)

CATEGORY_ALIAS_RULES: tuple[SpecAliasRule, ...] = (
    SpecAliasRule(
        raw_label="подсветка",
        canonical_label="подсветка",
        typed_field="display_tech",
        category_scope="tv",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="разъемы",
        canonical_label="разъемы",
        typed_field="hdmi",
        category_scope="tv",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
    SpecAliasRule(
        raw_label="hdmi порты",
        canonical_label="hdmi порты",
        typed_field="hdmi_count",
        category_scope="tv",
        store_scope=None,
        priority=10,
        is_deprecated=False,
    ),
)
