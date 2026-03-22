from __future__ import annotations

from unittest.mock import patch

from application.crm_sync_builder import build_payload_hash
from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle


def _norm(**kwargs):
    base = {
        "store": "s",
        "url": "https://x/p",
        "title": "T",
        "title_clean": "T",
        "source_id": "1",
        "external_ids": {"s": "1"},
        "price_raw": "1",
        "price_value": 10,
        "currency": "UZS",
        "in_stock": True,
        "raw_specs": {},
        "image_urls": [],
    }
    base.update(kwargs)
    return base


def _patch_lp(**kwargs):
    d = dict(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
        PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS=True,
        PARSER_FORCE_PRODUCT_FOUND_FALLBACK=True,
        PARSER_LIFECYCLE_DEFAULT_EVENT="product_found",
        PARSER_ENABLE_OUT_OF_STOCK_EVENT=False,
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=False,
    )
    d.update(kwargs)
    return patch.multiple("application.lifecycle.lifecycle_policy.settings", **d)


def _patch_crm():
    return patch.multiple(
        "application.crm_sync_builder.settings",
        MESSAGE_SCHEMA_VERSION=1,
        DEFAULT_CURRENCY="UZS",
        CRM_INCLUDE_SPEC_COVERAGE=False,
        CRM_INCLUDE_FIELD_CONFIDENCE=False,
        CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS=False,
        CRM_INCLUDE_NORMALIZATION_QUALITY=False,
    )


def test_payload_hash_unchanged_by_event_metadata():
    with _patch_crm(), _patch_lp():
        n = _norm(price_value=10)
        ple_pf, _ = build_lifecycle_event(n, {"crm_listing_id": "L1"}, "product_found")
        ple_pc, _ = build_lifecycle_event(n, {"crm_listing_id": "L1"}, "price_changed")
        assert ple_pf.payload_hash == ple_pc.payload_hash
        h_direct = build_payload_hash(
            schema_version=1,
            store="s",
            url="https://x/p",
            title="T",
            source_id="1",
            external_ids={"s": "1"},
            barcode=None,
            model_name=None,
            category_hint=None,
            price_raw="1",
            price_value=10,
            currency="UZS",
            in_stock=True,
            brand=None,
            raw_specs={},
            typed_specs={},
            normalization_warnings=[],
            description=None,
            image_urls=[],
        )
        assert ple_pf.payload_hash == h_direct


def test_parser_sync_event_includes_identity():
    with _patch_crm(), _patch_lp():
        ple, _ = build_lifecycle_event(_norm(), {"crm_listing_id": "L2"}, "product_found")
        ev = parser_sync_event_from_lifecycle(ple)
        assert ev.identity.crm_listing_id == "L2"
        assert ev.event_type == "product_found"
