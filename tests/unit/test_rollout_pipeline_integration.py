from __future__ import annotations

from unittest.mock import MagicMock

from config import settings as settings_mod

from application.extractors.spec_mapper import map_raw_specs_to_typed_partial
from application.lifecycle.lifecycle_policy import choose_lifecycle_event_type
from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_typed_specs_mapping_off_returns_empty_typed(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", False)

    def _off(name: str, *_a, **_kw):
        return name != "typed_specs_mapping"

    monkeypatch.setattr(
        "application.release.rollout_policy_engine.is_feature_enabled",
        _off,
    )
    tp, warns, meta = map_raw_specs_to_typed_partial(
        {"оперативная память": "8 GB"},
        "phone",
        store_name="mediapark",
        source_id="1",
        url="https://mediapark.uz/p/1",
    )
    assert tp.model_dump() == {} or not any(tp.model_dump().values())
    assert "typed_specs_mapping_disabled_by_rollout" in warns
    assert float(meta.get("mapping_ratio") or 0) == 0.0


def test_lifecycle_delta_off_forces_product_found(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", False)
    monkeypatch.setattr(settings_mod.settings, "PARSER_ENABLE_DELTA_EVENTS", True)
    monkeypatch.setattr(settings_mod.settings, "PARSER_ENABLE_RUNTIME_DELTA_EVENTS", True)
    monkeypatch.setattr(settings_mod.settings, "PARSER_ENABLE_PRICE_CHANGED_EVENT", True)

    def _off(name: str, *_a, **_kw):
        return name != "lifecycle_delta_events"

    monkeypatch.setattr(
        "application.release.rollout_policy_engine.is_feature_enabled",
        _off,
    )
    norm = {
        "store": "mediapark",
        "url": "https://mediapark.uz/p/1",
        "title": "P",
        "source_id": "1",
        "price_raw": "1",
        "price_value": 1,
        "currency": "UZS",
        "in_stock": True,
        "raw_specs": {},
        "typed_specs": {},
        "normalization_warnings": [],
        "spec_coverage": {},
        "field_confidence": {},
        "suppressed_typed_fields": [],
        "normalization_quality": {},
        "image_urls": [],
        "external_ids": {"mediapark": "1"},
        "entity_key": "mediapark:1",
        "payload_hash": "sha256:" + "a" * 64,
        "lifecycle_spec_update": True,
    }
    d = choose_lifecycle_event_type(norm, {"crm_listing_id": "L", "crm_product_id": "P"}, None)
    assert d.selected_event_type == "product_found"


def test_normalize_pipeline_hybrid_when_mapping_on(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", False)
    item = {
        "source": "mediapark",
        "url": "https://mediapark.uz/p/1",
        "title": "Смартфон Samsung Galaxy",
        "source_id": "99",
        "price_str": "1000 сум",
        "in_stock": True,
        "brand": "Samsung",
        "raw_specs": {"оперативная память": "8 GB", "встроенная память": "128 GB"},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="mediapark"))
    n = item["_normalized"]
    assert n["typed_specs"].get("ram_gb") == 8
