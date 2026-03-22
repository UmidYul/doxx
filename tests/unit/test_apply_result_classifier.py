from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from application.lifecycle import apply_result_classifier as arc_module
from application.lifecycle.apply_result_classifier import (
    classify_batch_sync_response,
    classify_single_sync_response,
    is_business_rejection,
    is_retryable_http_status,
)
from domain.crm_lifecycle import CrmIdentityContext
from domain.crm_sync import CrmSyncItem
from domain.crm_apply_result import MalformedCrmBatchResponse, summarize_batch_result
from domain.parser_event import ParserSyncEvent


def _item(**kw) -> CrmSyncItem:
    d = dict(
        schema_version=1,
        entity_key="mediapark:1",
        payload_hash="sha256:" + "a" * 64,
        source_name="mediapark",
        source_id="1",
        external_ids={"mediapark": "1"},
        source_url="https://mediapark.uz/p/1",
        title="Phone",
        price_value=10000,
        price_raw="10 000 сум",
        currency="UZS",
        in_stock=True,
        raw_specs={},
        image_urls=[],
        scraped_at=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
        sync_mode="snapshot",
    )
    d.update(kw)
    return CrmSyncItem(**d)


def _event(data: CrmSyncItem | None = None) -> ParserSyncEvent:
    d = data or _item()
    ident = CrmIdentityContext(
        entity_key=d.entity_key,
        external_ids=dict(d.external_ids or {}),
        barcode=d.barcode,
        source_name=d.source_name,
        source_url=d.source_url,
        source_id=d.source_id,
    )
    return ParserSyncEvent(
        event_id=str(uuid.uuid4()),
        event_type="product_found",
        identity=ident,
        payload_hash=d.payload_hash,
        data=d,
    )


def test_is_retryable_http_status() -> None:
    assert is_retryable_http_status(429) is True
    assert is_retryable_http_status(503) is True
    assert is_retryable_http_status(200) is False
    assert is_retryable_http_status(None) is False


def test_is_business_rejection() -> None:
    assert is_business_rejection(400) is True
    assert is_business_rejection(422) is True
    assert is_business_rejection(500) is False
    assert is_business_rejection(None, "VALIDATION_ERROR") is True


def test_single_http_200_requires_item_row() -> None:
    ev = _event()
    r = classify_single_sync_response(ev, 200, None)
    assert r.success is False
    assert r.status == "transport_failure"


def test_single_created_maps_status() -> None:
    ev = _event()
    r = classify_single_sync_response(
        ev,
        200,
        {"success": True, "action": "created", "crm_listing_id": "L1", "crm_product_id": "P1"},
    )
    assert r.success is True
    assert r.status == "created"
    assert r.crm_listing_id == "L1"


def test_needs_review_maps_matched() -> None:
    ev = _event()
    r = classify_single_sync_response(ev, 200, {"success": True, "action": "needs_review"})
    assert r.success is True
    assert r.status == "matched"


def test_ignored_respects_parser_mark_ignored() -> None:
    ev = _event()
    with patch.object(arc_module.settings, "PARSER_MARK_IGNORED_AS_APPLIED", True):
        r = classify_single_sync_response(ev, 200, {"success": True, "action": "ignored"})
        assert r.success is True
    with patch.object(arc_module.settings, "PARSER_MARK_IGNORED_AS_APPLIED", False):
        r = classify_single_sync_response(ev, 200, {"success": True, "action": "ignored"})
        assert r.success is False


def test_batch_mixed_results() -> None:
    evs = [_event(_item(entity_key=f"e:{i}", source_id=str(i))) for i in range(3)]
    body = {
        "results": [
            {"success": True, "action": "created"},
            {"success": False, "error_message": "no", "retryable": False},
            {"success": True, "action": "updated"},
        ]
    }
    with patch.object(arc_module.settings, "CRM_BATCH_REQUIRE_ITEM_RESULTS", True):
        batch = classify_batch_sync_response(evs, 200, body)
    s = summarize_batch_result(batch)
    assert s.succeeded == 2
    assert s.failed == 1
    assert batch.items[1].status == "rejected"


def test_batch_malformed_raises_when_required() -> None:
    evs = [_event(), _event(_item(entity_key="mediapark:2", source_id="2"))]
    with (
        patch.object(arc_module.settings, "CRM_BATCH_REQUIRE_ITEM_RESULTS", True),
        patch.object(arc_module.settings, "CRM_BATCH_STOP_ON_MALFORMED_RESPONSE", True),
    ):
        with pytest.raises(MalformedCrmBatchResponse):
            classify_batch_sync_response(evs, 200, {"results": [{"success": True}]})
