from __future__ import annotations

from unittest.mock import patch

from domain.crm_apply_result import CrmApplyResult
from domain.crm_lifecycle import CrmIdentityContext
from application.lifecycle.reconciliation import (
    decide_reconciliation,
    reconcile_after_ambiguous_response,
    reconcile_missing_ids,
)


def _id() -> CrmIdentityContext:
    return CrmIdentityContext(
        entity_key="s:1",
        external_ids={"s": "1"},
        source_name="s",
        source_url="https://x",
        source_id="1",
    )


def test_decide_missing_ids() -> None:
    r = CrmApplyResult(
        event_id="e",
        entity_key="s:1",
        payload_hash="h",
        success=True,
        status="created",
        parser_reconciliation_signal="missing_ids",
    )
    with patch.multiple(
        "application.lifecycle.reconciliation.settings",
        PARSER_RECONCILE_ON_MISSING_IDS=True,
        PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION=True,
    ):
        d = decide_reconciliation("product_found", r, None)
        assert d.should_reconcile is True
        assert d.reconcile_via == "runtime_ids"


def test_decide_response_lost() -> None:
    with patch.multiple(
        "application.lifecycle.reconciliation.settings",
        PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION=True,
    ):
        d = decide_reconciliation("price_changed", None, None)
        assert d.should_reconcile is True
        assert d.reconcile_via == "resend_product_found"


def test_reconcile_runtime_bridge() -> None:
    with patch.multiple(
        "application.lifecycle.reconciliation.settings",
        PARSER_ENABLE_RUNTIME_RECONCILIATION=True,
        PARSER_ENABLE_CATALOG_FIND_RECONCILIATION=False,
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
    ):
        rec = reconcile_missing_ids(
            _id(),
            {},
            runtime_ids={"crm_listing_id": "L9", "crm_product_id": "P9"},
            apply_result=None,
        )
        assert rec.resolved is True
        assert rec.source == "runtime"
        assert rec.crm_listing_id == "L9"


def test_catalog_find_disabled_by_default() -> None:
    with patch.multiple(
        "application.lifecycle.reconciliation.settings",
        PARSER_ENABLE_RUNTIME_RECONCILIATION=False,
        PARSER_ENABLE_CATALOG_FIND_RECONCILIATION=False,
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
    ):
        rec = reconcile_missing_ids(_id(), {}, runtime_ids=None, apply_result=None)
        assert rec.resolved is False
        assert any("resend" in n.lower() for n in rec.notes)


def test_reconcile_after_ambiguous() -> None:
    with patch.multiple(
        "application.lifecycle.reconciliation.settings",
        PARSER_ENABLE_RUNTIME_RECONCILIATION=True,
    ):
        rec = reconcile_after_ambiguous_response(
            _id(),
            {},
            runtime_ids={"crm_listing_id": "L1"},
        )
        assert rec.resolved is True
