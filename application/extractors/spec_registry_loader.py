from __future__ import annotations

from functools import lru_cache
from typing import Any

from config.settings import settings

from application.extractors import spec_registry_appliance as reg_app
from application.extractors import spec_registry_common as reg_common
from application.extractors import spec_registry_laptop as reg_laptop
from application.extractors import spec_registry_phone as reg_phone
from application.extractors import spec_registry_stores as reg_stores
from application.extractors import spec_registry_tablet as reg_tablet
from application.extractors import spec_registry_tv as reg_tv
from application.extractors import spec_registry_unknown as reg_unk
from application.extractors.spec_label_normalizer import normalize_spec_label
from application.extractors.spec_registry import (
    CategorySpecPolicy,
    SpecAliasRule,
    SpecFieldDefinition,
    StoreSpecOverride,
)

_CATEGORY_MODULES = (
    reg_phone,
    reg_tablet,
    reg_laptop,
    reg_tv,
    reg_app,
)


def _normalize_rule(r: SpecAliasRule) -> SpecAliasRule:
    nk = normalize_spec_label(r.raw_label)
    ck = normalize_spec_label(r.canonical_label) or nk
    return r.model_copy(update={"raw_label": nk, "canonical_label": ck})


def clear_spec_registry_cache() -> None:
    load_spec_registry.cache_clear()


@lru_cache(maxsize=1)
def load_spec_registry() -> dict[str, Any]:
    """Load and normalize the full spec registry (deterministic, cached)."""
    field_definitions: dict[str, SpecFieldDefinition] = dict(reg_common.FIELD_DEFINITIONS)

    alias_rules: list[SpecAliasRule] = []
    for r in reg_common.COMMON_ALIAS_RULES:
        alias_rules.append(_normalize_rule(r))
    for mod in _CATEGORY_MODULES:
        for r in getattr(mod, "CATEGORY_ALIAS_RULES", ()):
            alias_rules.append(_normalize_rule(r))

    if settings.ENABLE_STORE_SPEC_OVERRIDES:
        for ov in reg_stores.STORE_OVERRIDES:
            for r in ov.alias_overrides:
                alias_rules.append(_normalize_rule(r))

    category_policies: dict[str, CategorySpecPolicy] = {
        "phone": reg_phone.PHONE_CATEGORY_POLICY,
        "tablet": reg_tablet.TABLET_CATEGORY_POLICY,
        "laptop": reg_laptop.LAPTOP_CATEGORY_POLICY,
        "tv": reg_tv.TV_CATEGORY_POLICY,
        "appliance": reg_app.APPLIANCE_CATEGORY_POLICY,
        "unknown": reg_unk.UNKNOWN_CATEGORY_POLICY,
        "accessory": reg_unk.ACCESSORY_CATEGORY_POLICY,
    }

    store_overrides: tuple[StoreSpecOverride, ...] = (
        reg_stores.STORE_OVERRIDES if settings.ENABLE_STORE_SPEC_OVERRIDES else ()
    )

    return {
        "field_definitions": field_definitions,
        "alias_rules": tuple(alias_rules),
        "category_policies": category_policies,
        "store_overrides": store_overrides,
    }


def _cat_key(category_hint: str | None) -> str:
    c = (category_hint or "unknown").strip().lower()
    if c not in load_spec_registry()["category_policies"]:
        return "unknown"
    return c


def get_category_policy(category_hint: str | None) -> CategorySpecPolicy:
    reg = load_spec_registry()
    key = _cat_key(category_hint)
    return reg["category_policies"][key]


def get_field_definitions(category_hint: str | None) -> dict[str, SpecFieldDefinition]:
    reg = load_spec_registry()
    cat = _cat_key(category_hint)
    policy = reg["category_policies"][cat]
    out: dict[str, SpecFieldDefinition] = {}
    for name, fd in reg["field_definitions"].items():
        if name in policy.enabled_fields:
            if cat in fd.supported_categories or "unknown" in fd.supported_categories:
                out[name] = fd
    return out


def get_store_overrides(store_name: str, category_hint: str | None = None) -> StoreSpecOverride | None:
    if not settings.ENABLE_STORE_SPEC_OVERRIDES:
        return None
    st = (store_name or "").strip().lower()
    if not st:
        return None
    cat = (category_hint or "").strip().lower() or None
    reg = load_spec_registry()
    matches: list[StoreSpecOverride] = []
    for ov in reg["store_overrides"]:
        if ov.store_name.lower() != st:
            continue
        if ov.category_hint is None:
            matches.append(ov)
        elif ov.category_hint.lower() == cat:
            matches.append(ov)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Merge: category-specific wins over store-wide (None).
    specific = [o for o in matches if o.category_hint is not None]
    if specific:
        return specific[0]
    return matches[0]


def _rule_sort_key(r: SpecAliasRule) -> tuple[int, int, int, str]:
    return (
        -r.priority,
        0 if r.store_scope else 1,
        0 if r.category_scope else 1,
        r.typed_field,
    )


def _merged_field_disables(store_name: str, category_hint: str | None) -> frozenset[str]:
    if not settings.ENABLE_STORE_SPEC_OVERRIDES:
        return frozenset()
    st = (store_name or "").strip().lower()
    reg = load_spec_registry()
    out: set[str] = set()
    ch = (category_hint or "").strip().lower() or None
    for ov in reg["store_overrides"]:
        if ov.store_name.lower() != st:
            continue
        if ov.category_hint is None:
            out |= set(ov.field_disables)
        elif ch is not None and ov.category_hint.lower() == ch:
            out |= set(ov.field_disables)
    return frozenset(out)


def get_alias_rules(
    category_hint: str | None,
    store_name: str | None = None,
) -> list[SpecAliasRule]:
    """All rules applicable to (category, store), sorted for deterministic merge (highest priority first)."""
    reg = load_spec_registry()
    cat = _cat_key(category_hint)
    st = (store_name or "").strip().lower() or None

    rules: list[SpecAliasRule] = []
    for r in reg["alias_rules"]:
        if r.category_scope is not None and r.category_scope.lower() != cat:
            continue
        if r.store_scope is not None:
            if st is None or r.store_scope.lower() != st:
                continue
        rules.append(r)

    return sorted(rules, key=_rule_sort_key)


def get_rules_index(
    category_hint: str | None,
    store_name: str | None = None,
) -> dict[str, list[SpecAliasRule]]:
    """normalized_label -> rules (sorted highest priority first)."""
    idx: dict[str, list[SpecAliasRule]] = {}
    for r in get_alias_rules(category_hint, store_name):
        idx.setdefault(r.raw_label, []).append(r)
    for k in idx:
        idx[k].sort(key=_rule_sort_key)
    return idx


def merged_field_disables(store_name: str, category_hint: str | None) -> frozenset[str]:
    return _merged_field_disables(store_name, category_hint)
