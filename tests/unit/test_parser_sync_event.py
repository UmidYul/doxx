from __future__ import annotations

from unittest.mock import patch

from application.crm_sync_builder import build_parser_sync_event
from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle


def _norm(**kwargs):
    base = {
        "store": "mediapark",
        "url": "https://mediapark.uz/p/1",
        "title": "Phone",
        "title_clean": "Phone",
        "source_id": "1",
        "external_ids": {"mediapark": "1"},
        "price_raw": "10 сум",
        "price_value": 10,
        "currency": "UZS",
        "in_stock": True,
        "brand": None,
        "category_hint": "unknown",
        "barcode": None,
        "model_name": None,
        "raw_specs": {},
        "description": None,
        "image_urls": [],
    }
    base.update(kwargs)
    return base


def _lp_settings(**kwargs):
    return patch.multiple(
        "application.lifecycle.lifecycle_policy.settings",
        PARSER_LIFECYCLE_DEFAULT_EVENT="product_found",
        PARSER_FORCE_PRODUCT_FOUND_FALLBACK=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=kwargs.get("PARSER_ENABLE_RUNTIME_DELTA_EVENTS", False),
        PARSER_ENABLE_DELTA_EVENTS=kwargs.get("PARSER_ENABLE_DELTA_EVENTS", False),
        PARSER_ENABLE_PRICE_CHANGED_EVENT=kwargs.get("PARSER_ENABLE_PRICE_CHANGED_EVENT", False),
        PARSER_ENABLE_OUT_OF_STOCK_EVENT=kwargs.get("PARSER_ENABLE_OUT_OF_STOCK_EVENT", False),
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=kwargs.get("PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT", False),
        PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS=kwargs.get(
            "PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS", True
        ),
        PARSER_ALLOW_OUT_OF_STOCK_WITH_RUNTIME_IDS=kwargs.get(
            "PARSER_ALLOW_OUT_OF_STOCK_WITH_RUNTIME_IDS", True
        ),
        PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS=kwargs.get(
            "PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS", False
        ),
    )


def _crm_settings():
    return patch.multiple(
        "application.crm_sync_builder.settings",
        MESSAGE_SCHEMA_VERSION=1,
        DEFAULT_CURRENCY="UZS",
        CRM_INCLUDE_SPEC_COVERAGE=False,
        CRM_INCLUDE_FIELD_CONFIDENCE=False,
        CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS=False,
        CRM_INCLUDE_NORMALIZATION_QUALITY=False,
    )


def test_delta_events_disabled_always_product_found() -> None:
    with _crm_settings(), _lp_settings(
        PARSER_ENABLE_DELTA_EVENTS=False,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
        PARSER_ENABLE_OUT_OF_STOCK_EVENT=True,
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=True,
    ):
        ev = build_parser_sync_event(_norm(price_value=999))
        assert ev.event_type == "product_found"


def test_event_id_unique_per_build() -> None:
    with _crm_settings(), _lp_settings():
        a = build_parser_sync_event(_norm())
        b = build_parser_sync_event(_norm())
        assert a.event_id != b.event_id


def test_payload_hash_stable_in_data_matches_top_level() -> None:
    with _crm_settings(), _lp_settings():
        ev = build_parser_sync_event(_norm())
        assert ev.data.payload_hash.startswith("sha256:")
        assert ev.data.payload_hash != ev.event_id
        assert ev.payload_hash == ev.data.payload_hash


def test_price_changed_requires_runtime_listing_id() -> None:
    with _crm_settings(), _lp_settings(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
    ):
        ple, _dec = build_lifecycle_event(_norm(price_value=42), runtime_ids=None, requested_event_type=None)
        ev = parser_sync_event_from_lifecycle(ple)
        assert ev.event_type == "product_found"


def test_price_changed_allowed_with_runtime_listing_id() -> None:
    with _crm_settings(), _lp_settings(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
    ):
        ple, dec = build_lifecycle_event(
            _norm(price_value=42),
            runtime_ids={"crm_listing_id": "L1"},
            requested_event_type=None,
        )
        ev = parser_sync_event_from_lifecycle(ple)
        assert ev.event_type == "price_changed"
        assert dec.fallback_applied is False
