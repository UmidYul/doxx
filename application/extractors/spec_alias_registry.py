from __future__ import annotations

"""Backward-compatible facade over the central spec registry (3B)."""

from application.extractors.spec_label_normalizer import normalize_spec_label
from application.extractors.spec_registry_loader import get_rules_index


def merge_aliases_for_category(category_hint: str | None) -> dict[str, str]:
    """Highest-priority alias per normalized label (common + category, no store)."""
    idx = get_rules_index(category_hint, None)
    return {label: rules[0].typed_field for label, rules in idx.items() if rules}


def normalize_label_key(label: str) -> str:
    return normalize_spec_label(label)
