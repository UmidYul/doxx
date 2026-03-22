from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult
from infrastructure.pipelines.sync_pipeline import SyncPipeline
from tests.unit.batch_apply_helpers import crm_apply_ok


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
    return {"url": base["url"], "_normalized": base}


@pytest.mark.asyncio
async def test_same_idempotency_key_across_two_builds_same_snapshot() -> None:
    with patch.multiple(
        "application.lifecycle.replay_policy.settings",
        PARSER_IDEMPOTENCY_SCOPE_DEFAULT="entity_payload",
        PARSER_REPLAY_MODE_DEFAULT="snapshot_upsert",
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
        PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS=False,
    ):
        from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle

        n = _norm()
        p1, _ = build_lifecycle_event(n, None, None)
        p2, _ = build_lifecycle_event(n, None, None)
        e1 = parser_sync_event_from_lifecycle(p1, normalized_for_reconcile=dict(n))
        e2 = parser_sync_event_from_lifecycle(p2, normalized_for_reconcile=dict(n))
        assert e1.request_idempotency_key == e2.request_idempotency_key
        assert e1.event_id != e2.event_id


@pytest.mark.asyncio
async def test_reconcile_resend_bounded_no_infinite_loop() -> None:
    transport = AsyncMock()

    async def _missing_ids(ev):
        e = ev[0]
        return CrmBatchApplyResult(
            items=[
                CrmApplyResult(
                    event_id=e.event_id,
                    entity_key=e.data.entity_key,
                    payload_hash=e.data.payload_hash,
                    success=True,
                    status="created",
                    http_status=200,
                    action="created",
                    parser_reconciliation_signal="missing_ids",
                )
            ],
            transport_ok=True,
            http_status=200,
        )

    transport.send_batch_events = AsyncMock(side_effect=_missing_ids)
    transport.close = AsyncMock()
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1
    with patch.multiple(
        "infrastructure.pipelines.sync_pipeline.settings",
        CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD=False,
        SYNC_BUFFER_FLUSH_SECONDS=0.0,
        PARSER_MAX_EVENT_ATTEMPTS_PER_RUN=5,
        PARSER_RECONCILE_MAX_ATTEMPTS_PER_RUN=1,
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
        PARSER_ENABLE_RUNTIME_RECONCILIATION=True,
        PARSER_RECONCILE_ON_MISSING_IDS=True,
    ):
        await pipe.process_item(_norm(), MagicMock())
        await pipe.close_spider(MagicMock())
    assert transport.send_batch_events.await_count >= 1
    assert pipe._reconcile_resend_counts.get("mediapark:1", 0) <= 1


@pytest.mark.asyncio
async def test_runtime_ids_resolve_reconciliation_in_memory() -> None:
    transport = AsyncMock()
    _state = {"n": 0}

    async def _missing_then_ok(ev):
        e = ev[0]
        _state["n"] += 1
        if _state["n"] == 1:
            return CrmBatchApplyResult(
                items=[
                    CrmApplyResult(
                        event_id=e.event_id,
                        entity_key=e.data.entity_key,
                        payload_hash=e.data.payload_hash,
                        success=True,
                        status="created",
                        http_status=200,
                        parser_reconciliation_signal="missing_ids",
                    )
                ],
                transport_ok=True,
                http_status=200,
            )
        return CrmBatchApplyResult(items=[crm_apply_ok(e)], transport_ok=True, http_status=200)
    transport.send_batch_events = AsyncMock(side_effect=_missing_then_ok)
    transport.close = AsyncMock()
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1
    pipe._identity_bridge.remember_apply_result(
        CrmApplyResult(
            event_id="x",
            entity_key="mediapark:1",
            payload_hash="h",
            success=True,
            status="created",
            crm_listing_id="LFIX",
            crm_product_id="PFIX",
        )
    )
    with patch.multiple(
        "infrastructure.pipelines.sync_pipeline.settings",
        CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD=False,
        SYNC_BUFFER_FLUSH_SECONDS=0.0,
        PARSER_MAX_EVENT_ATTEMPTS_PER_RUN=5,
        PARSER_RECONCILE_MAX_ATTEMPTS_PER_RUN=0,
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=False,
        PARSER_ENABLE_RUNTIME_RECONCILIATION=True,
    ):
        await pipe.process_item(_norm(), MagicMock())
    rec = pipe._replay_journal.get_reconciliation("mediapark:1")
    assert rec is not None
    assert rec.resolved is True
