from __future__ import annotations

import pytest

from application.crm_sync_builder import (
    build_crm_sync_item,
    build_entity_key,
    build_payload_hash,
    canonicalize_url,
    _compute_change_hint,
)


def _ph(**kwargs):
    base = dict(
        schema_version=1,
        store="s",
        url="https://x",
        title="T",
        source_id="1",
        external_ids={},
        barcode=None,
        model_name=None,
        category_hint=None,
        price_raw=None,
        price_value=None,
        currency="UZS",
        in_stock=True,
        brand=None,
        raw_specs={},
        typed_specs={},
        normalization_warnings=[],
        description=None,
        image_urls=[],
    )
    base.update(kwargs)
    return build_payload_hash(**base)


# ---- canonicalize_url ----

def test_canonicalize_strips_query_and_fragment():
    assert canonicalize_url("https://Mediapark.uz/path/?q=1#top") == "https://mediapark.uz/path/"


def test_canonicalize_lowercases_netloc():
    assert canonicalize_url("https://MEDIAPARK.UZ/P") == "https://mediapark.uz/P"


# ---- entity_key stability ----

def test_entity_key_store_plus_source_id():
    assert build_entity_key("mediapark", "abc-123", "https://x/y") == "mediapark:abc-123"


def test_entity_key_falls_back_to_url_hash():
    k1 = build_entity_key("mediapark", None, "https://mediapark.uz/path/")
    k2 = build_entity_key("mediapark", "", "https://mediapark.uz/path/")
    assert k1 == k2
    assert k1.startswith("mediapark:")
    assert len(k1) > len("mediapark:")


def test_entity_key_is_deterministic():
    for _ in range(5):
        assert build_entity_key("s", "id1", "https://x") == "s:id1"


# ---- payload_hash ----

def test_payload_hash_stable():
    h1 = _ph(
        store="mediapark",
        url="https://example.com/p",
        title="Phone",
        source_id="1",
        price_raw="10 sum",
        price_value=10,
        brand="Samsung",
        raw_specs={"ram": "8"},
        description="desc",
        image_urls=["https://img/1.jpg"],
    )
    h2 = _ph(
        store="mediapark",
        url="https://example.com/p",
        title="Phone",
        source_id="1",
        price_raw="10 sum",
        price_value=10,
        brand="Samsung",
        raw_specs={"ram": "8"},
        description="desc",
        image_urls=["https://img/1.jpg"],
    )
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_payload_hash_changes_on_price_value():
    h1 = _ph(price_raw="10", price_value=10, brand="X")
    assert _ph(price_raw="10", price_value=20, brand="X") != h1


def test_payload_hash_changes_on_in_stock():
    h1 = _ph(in_stock=True)
    assert _ph(in_stock=False) != h1


def test_payload_hash_deduplicates_and_sorts_image_urls():
    h1 = _ph(image_urls=["https://b.jpg", "https://a.jpg", "https://b.jpg"])
    h2 = _ph(image_urls=["https://a.jpg", "https://b.jpg"])
    assert h1 == h2


def test_payload_hash_includes_external_ids():
    h1 = _ph(external_ids={"mediapark": "1"})
    assert _ph(external_ids={"mediapark": "2"}) != h1


def test_payload_hash_includes_typed_specs_and_warnings():
    h0 = _ph()
    assert _ph(typed_specs={"ram_gb": 8}) != h0
    assert _ph(normalization_warnings=["ram_storage_swap_suspected"]) != h0


def test_build_crm_sync_item_includes_spec_coverage_when_present():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "raw_specs": {},
        "spec_coverage": {"mapping_ratio": 0.5, "total_raw_fields": 2},
    }
    item = build_crm_sync_item(norm)
    assert item.spec_coverage.get("mapping_ratio") == 0.5


def test_build_crm_sync_item_includes_normalized_spec_labels():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "raw_specs": {
            "Емкость аккумулятора\\t": "5000 mAh",
            "Стандарт Bluetooth": "5.3",
        },
    }
    item = build_crm_sync_item(norm)
    assert item.normalized_spec_labels.get("Емкость аккумулятора\\t") == "емкость аккумулятора"
    assert item.normalized_spec_labels.get("Стандарт Bluetooth") == "стандарт bluetooth"


def test_build_crm_sync_item_includes_compatibility_targets_for_accessory():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "Case for Samsung Galaxy S24",
        "category_hint": "accessory",
        "raw_specs": {},
    }
    item = build_crm_sync_item(norm)
    assert item.compatibility_targets == ["Samsung Galaxy S24"]


def test_build_crm_sync_item_compatibility_targets_empty_for_non_accessory():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "Samsung Galaxy S24",
        "category_hint": "phone",
        "raw_specs": {},
    }
    item = build_crm_sync_item(norm)
    assert item.compatibility_targets == []


def test_build_crm_sync_item_includes_compatibility_targets_from_raw_specs():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "Spigen Rugged Armor",
        "category_hint": "accessory",
        "raw_specs": {"Compatible with": "Samsung Galaxy S24, Galaxy S24+"},
    }
    item = build_crm_sync_item(norm)
    assert item.compatibility_targets == ["Samsung Galaxy S24", "Galaxy S24+"]


# ---- change_hint ----

def test_change_hint_stock_update_when_out_of_stock():
    assert _compute_change_hint(price_value=100, in_stock=False, raw_specs={"a": "b"}) == "stock_update"


def test_change_hint_price_update_when_price_present():
    assert _compute_change_hint(price_value=100, in_stock=True, raw_specs={}) == "price_update"


def test_change_hint_new_product_when_no_price_no_specs():
    assert _compute_change_hint(price_value=None, in_stock=True, raw_specs={}) == "new_product"


def test_change_hint_none_when_no_price_but_specs():
    assert _compute_change_hint(price_value=None, in_stock=True, raw_specs={"a": "b"}) is None


# ---- build_crm_sync_item ----

def test_build_crm_sync_item_snapshot_mode():
    norm = {
        "store": "mediapark",
        "url": "https://mediapark.uz/p",
        "title": "  Test Phone  ",
        "title_clean": "Test Phone",
        "source_id": "42",
        "external_ids": {"mediapark": "42"},
        "price_raw": "10 000 сум",
        "price_value": 10000,
        "currency": "UZS",
        "in_stock": True,
        "brand": "Samsung",
        "category_hint": "phone",
        "raw_specs": {},
        "description": None,
        "image_urls": [],
    }
    item = build_crm_sync_item(norm)
    assert item.sync_mode == "snapshot"
    assert item.typed_specs == {}
    assert item.normalized_spec_labels == {}
    assert item.compatibility_targets == []
    assert item.normalization_warnings == []
    assert item.spec_coverage == {}
    assert item.entity_key == "mediapark:42"
    assert item.payload_hash.startswith("sha256:")
    assert item.source_name == "mediapark"
    assert item.title == "Test Phone"
    assert item.price_value == 10000
    assert item.external_ids == {"mediapark": "42"}
    assert item.change_hint == "price_update"


def test_build_crm_sync_item_out_of_stock_hint():
    norm = {"store": "s", "url": "https://x", "title": "T", "in_stock": False, "raw_specs": {}}
    assert build_crm_sync_item(norm).change_hint == "stock_update"


def test_build_crm_sync_item_new_product_hint():
    norm = {"store": "s", "url": "https://x", "title": "T", "raw_specs": {}}
    assert build_crm_sync_item(norm).change_hint == "new_product"


def test_build_crm_sync_item_uses_category_hint_field_not_raw_specs():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "category_hint": "laptop",
        "raw_specs": {"_category_hint": "ignored_on_normalized", "ram": "8"},
    }
    item = build_crm_sync_item(norm)
    assert item.category_hint == "laptop"
    assert "_category_hint" not in item.raw_specs
    assert "_category_hint" not in item.normalized_spec_labels
    assert item.normalized_spec_labels.get("ram") == "ram"


def test_build_crm_sync_item_legacy_price_float_fallback():
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "price": 99.0,
        "raw_specs": {},
    }
    assert build_crm_sync_item(norm).price_value == 99


def test_build_crm_sync_item_includes_normalization_metadata_when_enabled(monkeypatch: pytest.MonkeyPatch):
    from application import crm_sync_builder as b

    monkeypatch.setattr(b.settings, "CRM_INCLUDE_FIELD_CONFIDENCE", True)
    monkeypatch.setattr(b.settings, "CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS", True)
    monkeypatch.setattr(b.settings, "CRM_INCLUDE_NORMALIZATION_QUALITY", True)
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "raw_specs": {},
        "field_confidence": {"ram_gb": {"confidence": 0.9}},
        "suppressed_typed_fields": [{"field_name": "x", "reason_code": "suppressed_by_conflict"}],
        "normalization_quality": {"warning_count": 1},
    }
    item = build_crm_sync_item(norm)
    assert item.field_confidence.get("ram_gb", {}).get("confidence") == 0.9
    assert item.suppressed_typed_fields
    assert item.normalization_quality.get("warning_count") == 1


def test_build_crm_sync_item_omits_metadata_when_flags_off(monkeypatch: pytest.MonkeyPatch):
    from application import crm_sync_builder as b

    monkeypatch.setattr(b.settings, "CRM_INCLUDE_FIELD_CONFIDENCE", False)
    monkeypatch.setattr(b.settings, "CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS", False)
    monkeypatch.setattr(b.settings, "CRM_INCLUDE_NORMALIZATION_QUALITY", False)
    norm = {
        "store": "s",
        "url": "https://x",
        "title": "T",
        "raw_specs": {},
        "field_confidence": {"ram_gb": {"confidence": 0.9}},
        "suppressed_typed_fields": [{"field_name": "x"}],
        "normalization_quality": {"warning_count": 1},
    }
    item = build_crm_sync_item(norm)
    assert item.field_confidence == {}
    assert item.suppressed_typed_fields == []
    assert item.normalization_quality == {}
