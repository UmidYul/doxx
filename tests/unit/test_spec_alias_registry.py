from __future__ import annotations

from application.extractors.spec_alias_registry import (
    merge_aliases_for_category,
    normalize_label_key,
)


def test_normalize_label_key():
    assert normalize_label_key("  ОЗУ ") == "озу"


def test_merge_aliases_laptop_overrides_common_weight():
    m = merge_aliases_for_category("laptop")
    assert m["вес"] == "weight_kg"
    assert m["оперативная память"] == "ram_gb"


def test_merge_aliases_tv_adds_keys():
    m = merge_aliases_for_category("tv")
    assert m["диагональ экрана"] == "display_size_inch"
    assert "подсветка" in m
