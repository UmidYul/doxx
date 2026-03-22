from __future__ import annotations

"""Store-level alias overrides and field governance (no spider hardcoding)."""

from application.extractors.spec_registry import SpecAliasRule, StoreSpecOverride

# Mediapark PDP tables / RU JSON-style labels (higher priority than common where overlapping).
MEDIAPARK_OVERRIDES: tuple[StoreSpecOverride, ...] = (
    StoreSpecOverride(
        store_name="mediapark",
        category_hint=None,
        alias_overrides=(
            SpecAliasRule(
                raw_label="тип sim-карты",
                canonical_label="тип sim-карты",
                typed_field="sim_count",
                category_scope=None,
                store_scope="mediapark",
                priority=80,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="объем оперативной памяти",
                canonical_label="объем оперативной памяти",
                typed_field="ram_gb",
                category_scope=None,
                store_scope="mediapark",
                priority=80,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="объём оперативной памяти",
                canonical_label="объём оперативной памяти",
                typed_field="ram_gb",
                category_scope=None,
                store_scope="mediapark",
                priority=80,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="объем жесткого диска",
                canonical_label="объем жесткого диска",
                typed_field="storage_gb",
                category_scope=None,
                store_scope="mediapark",
                priority=80,
                is_deprecated=False,
            ),
        ),
        field_disables=frozenset(),
        field_priorities={},
    ),
)

# Uzum: noisy marketplace keys — weak structure; boost generic English hints; disable ambiguous hdmi bool.
UZUM_OVERRIDES: tuple[StoreSpecOverride, ...] = (
    StoreSpecOverride(
        store_name="uzum",
        category_hint=None,
        alias_overrides=(
            SpecAliasRule(
                raw_label="memory",
                canonical_label="memory",
                typed_field="storage_gb",
                category_scope=None,
                store_scope="uzum",
                priority=70,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="ram",
                canonical_label="ram",
                typed_field="ram_gb",
                category_scope=None,
                store_scope="uzum",
                priority=75,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="display",
                canonical_label="display",
                typed_field="display_size_inch",
                category_scope=None,
                store_scope="uzum",
                priority=60,
                is_deprecated=False,
            ),
            SpecAliasRule(
                raw_label="screen",
                canonical_label="screen",
                typed_field="display_size_inch",
                category_scope=None,
                store_scope="uzum",
                priority=55,
                is_deprecated=False,
            ),
        ),
        field_disables=frozenset({"hdmi"}),
        field_priorities={},
    ),
)

STORE_OVERRIDES: tuple[StoreSpecOverride, ...] = MEDIAPARK_OVERRIDES + UZUM_OVERRIDES
