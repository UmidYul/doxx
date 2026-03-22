from __future__ import annotations

from unittest.mock import patch

from application.lifecycle.lifecycle_policy import (
    build_identity_context,
    can_emit_event,
    choose_lifecycle_event_type,
    should_fallback_to_product_found,
)
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
    defaults = dict(
        PARSER_ENABLE_DELTA_EVENTS=False,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=False,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=False,
        PARSER_ENABLE_OUT_OF_STOCK_EVENT=False,
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=False,
        PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS=True,
        PARSER_ALLOW_OUT_OF_STOCK_WITH_RUNTIME_IDS=True,
        PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS=False,
        PARSER_FORCE_PRODUCT_FOUND_FALLBACK=True,
        PARSER_LIFECYCLE_DEFAULT_EVENT="product_found",
    )
    defaults.update(kwargs)
    return patch.multiple("application.lifecycle.lifecycle_policy.settings", **defaults)


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


def test_build_identity_context_merges_runtime_ids():
    with _patch_crm():
        ctx = build_identity_context(_norm(), {"crm_listing_id": "L1", "crm_product_id": "P1"})
        assert ctx.entity_key == "s:1"
        assert ctx.crm_listing_id == "L1"
        assert ctx.crm_product_id == "P1"


def test_without_runtime_ids_choose_product_found_for_price_hint():
    with _patch_crm(), _patch_lp(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
    ):
        d = choose_lifecycle_event_type(_norm(price_value=99), None, None)
        assert d.selected_event_type == "product_found"
        assert d.fallback_applied is True


def test_price_changed_blocked_records_required_ids():
    with _patch_crm(), _patch_lp(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_PRICE_CHANGED_EVENT=True,
    ):
        dec = can_emit_event("price_changed", build_identity_context(_norm(), None), _norm())
        assert dec.allowed is False
        assert "crm_listing_id" in dec.required_ids


def test_out_of_stock_blocked_without_listing():
    with _patch_crm(), _patch_lp(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_OUT_OF_STOCK_EVENT=True,
    ):
        n = _norm(in_stock=False)
        dec = choose_lifecycle_event_type(n, None, None)
        assert dec.selected_event_type == "product_found"


def test_characteristic_added_blocked_without_product_id():
    with _patch_crm(), _patch_lp(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=True,
        PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS=True,
    ):
        n = _norm(lifecycle_spec_update=True)
        dec = choose_lifecycle_event_type(n, None, "characteristic_added")
        assert dec.selected_event_type == "product_found"


def test_characteristic_allowed_with_product_id_and_signal():
    with _patch_crm(), _patch_lp(
        PARSER_ENABLE_DELTA_EVENTS=True,
        PARSER_ENABLE_RUNTIME_DELTA_EVENTS=True,
        PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT=True,
        PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS=True,
    ):
        n = _norm(lifecycle_spec_update=True)
        dec = choose_lifecycle_event_type(
            n,
            {"crm_product_id": "P9"},
            "characteristic_added",
        )
        assert dec.selected_event_type == "characteristic_added"
        assert dec.fallback_applied is False


def test_should_fallback_to_product_found():
    assert should_fallback_to_product_found(
        choose_lifecycle_event_type(_norm(price_value=1), None, "price_changed")
    ) is True


def test_catalog_precheck_disabled_by_default():
    from application.lifecycle import catalog_precheck as cp
    from domain.crm_lifecycle import CrmIdentityContext

    with patch.object(cp.settings, "PARSER_USE_CATALOG_FIND_PRECHECK", False):
        ctx = CrmIdentityContext(
            entity_key="s:1",
            external_ids={},
            source_name="s",
            source_url="https://x",
        )
        assert cp.should_use_catalog_precheck(ctx) is False
