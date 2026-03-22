from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ValueType = Literal["int", "float", "str", "bool"]


class SpecFieldDefinition(BaseModel):
    """Typed field metadata: normalizer + plausibility + category support."""

    model_config = ConfigDict(frozen=True)

    field_name: str
    value_type: ValueType
    supported_categories: frozenset[str] = Field(
        default_factory=lambda: frozenset(
            {"phone", "tablet", "laptop", "tv", "appliance", "accessory", "unknown"}
        )
    )
    normalizer_name: str
    plausibility_checker: str | None = None
    priority: int = 0
    synonyms: tuple[str, ...] = ()


class SpecAliasRule(BaseModel):
    """Maps a raw catalog label (after label normalization) to a typed field."""

    model_config = ConfigDict(frozen=True)

    raw_label: str
    canonical_label: str
    typed_field: str
    category_scope: str | None = None
    store_scope: str | None = None
    priority: int = 0
    is_deprecated: bool = False


class CategorySpecPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    category_hint: str
    enabled_fields: frozenset[str]
    preferred_aliases: tuple[str, ...] = ()
    conflict_resolution_order: tuple[str, ...] = ()
    extraction_priority_order: tuple[str, ...] = ()


class StoreSpecOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    store_name: str
    category_hint: str | None = None
    alias_overrides: tuple[SpecAliasRule, ...] = ()
    field_disables: frozenset[str] = frozenset()
    field_priorities: dict[str, int] = Field(default_factory=dict)
