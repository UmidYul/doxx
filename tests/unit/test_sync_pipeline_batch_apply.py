from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult, MalformedCrmBatchResponse
from infrastructure.pipelines.sync_pipeline import SyncPipeline
from tests.unit.batch_apply_helpers import batch_mirror_success, crm_apply_fail, crm_apply_ok


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


def _transport() -> AsyncMock:
    t = AsyncMock()
    t.close = AsyncMock()
    return t


@pytest.mark.asyncio
async def test_batch_all_success_remembered_in_registry_and_bridge() -> None:
    t = _transport()

    async def _mirror(evts):
        return batch_mirror_success(evts)

    t.send_batch_events = AsyncMock(side_effect=_mirror)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._registry.get_crm_ids("mediapark:1") == ("l1", "p1")
    assert pipe._identity_bridge.has_listing_id("mediapark:1")


@pytest.mark.asyncio
async def test_mixed_batch_only_successful_remembered() -> None:
    t = _transport()
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    pipe._transport = t
    pipe._batch_size = 3

    async def _mixed(evts):
        return CrmBatchApplyResult(
            items=[
                crm_apply_ok(evts[0], crm_listing_id="L0", crm_product_id="P0"),
                crm_apply_fail(evts[1], retryable=False),
                crm_apply_ok(evts[2], crm_listing_id="L2", crm_product_id="P2"),
            ],
            transport_ok=True,
            http_status=200,
        )

    t.send_batch_events = AsyncMock(side_effect=_mixed)
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        for i in range(3):
            await pipe.process_item(_norm(source_id=str(i)), MagicMock())
    assert pipe._registry.get_crm_ids("mediapark:0")[0] == "L0"
    assert pipe._registry.get_crm_ids("mediapark:1") == (None, None)
    assert pipe._registry.get_crm_ids("mediapark:2")[0] == "L2"


@pytest.mark.asyncio
async def test_retryable_requeued_then_succeeds_second_flush() -> None:
    t = _transport()
    calls: list[int] = []

    async def _side(evts):
        calls.append(len(evts))
        if len(calls) == 1:
            return CrmBatchApplyResult(
                items=[crm_apply_fail(evts[0], retryable=True, status="retryable_failure")],
                transport_ok=True,
                http_status=200,
            )
        return batch_mirror_success(evts)

    t.send_batch_events = AsyncMock(side_effect=_side)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS = True
        s.PARSER_REQUEUE_RETRYABLE_ONCE = True
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        await pipe.process_item(_norm(), MagicMock())
        await pipe.close_spider(MagicMock())
    assert t.send_batch_events.await_count == 2
    assert pipe._metrics.batch_items_requeued_total >= 1


@pytest.mark.asyncio
async def test_rejected_not_requeued() -> None:
    t = _transport()

    async def _one(evts):
        return CrmBatchApplyResult(
            items=[crm_apply_fail(evts[0], retryable=False)],
            transport_ok=True,
            http_status=200,
        )

    t.send_batch_events = AsyncMock(side_effect=_one)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS = True
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._metrics.batch_items_requeued_total == 0


@pytest.mark.asyncio
async def test_runtime_skip_same_entity_same_payload() -> None:
    t = _transport()
    t.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = True
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        await pipe.process_item(_norm(), MagicMock())
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._metrics.duplicate_payload_skips_total == 1
    assert t.send_batch_events.await_count == 1


@pytest.mark.asyncio
async def test_max_attempts_stops_requeue_loop() -> None:
    t = _transport()

    async def _fail(evts):
        return CrmBatchApplyResult(
            items=[crm_apply_fail(evts[0], retryable=True, status="retryable_failure")],
            transport_ok=True,
            http_status=200,
        )

    t.send_batch_events = AsyncMock(side_effect=_fail)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS = True
        s.PARSER_REQUEUE_RETRYABLE_ONCE = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 2
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        await pipe.process_item(_norm(), MagicMock())
        await pipe.close_spider(MagicMock())
    assert t.send_batch_events.await_count == 2


@pytest.mark.asyncio
async def test_malformed_batch_soft_policy_processes_synth() -> None:
    t = _transport()

    async def _raise(ev):
        inner = CrmBatchApplyResult(
            items=[
                CrmApplyResult(
                    event_id=ev[0].event_id,
                    entity_key=ev[0].data.entity_key,
                    payload_hash=ev[0].data.payload_hash,
                    success=False,
                    status="transport_failure",
                    http_status=200,
                    retryable=False,
                    error_code="missing_item_result",
                )
            ],
            transport_ok=False,
            http_status=200,
            batch_error_code="malformed_batch_response",
        )
        raise MalformedCrmBatchResponse("x", batch=inner)

    t.send_batch_events = AsyncMock(side_effect=_raise)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_BATCH_STOP_ON_MALFORMED_RESPONSE = False
        s.TRANSPORT_FAIL_FAST = False
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._metrics.malformed_batch_responses_total == 1


@pytest.mark.asyncio
async def test_close_spider_drains_retry_and_pending() -> None:
    t = _transport()
    t.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    pipe._transport = t
    pipe._batch_size = 50
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        await pipe.process_item(_norm(), MagicMock())
    t.send_batch_events.assert_not_awaited()
    await pipe.close_spider(MagicMock())
    t.send_batch_events.assert_awaited()


@pytest.mark.asyncio
async def test_malformed_stop_raises() -> None:
    t = _transport()

    async def _raise(ev):
        inner = CrmBatchApplyResult(
            items=[crm_apply_fail(ev[0], retryable=False, status="transport_failure")],
            transport_ok=False,
            http_status=200,
            batch_error_code="malformed_batch_response",
        )
        raise MalformedCrmBatchResponse("bad", batch=inner)

    t.send_batch_events = AsyncMock(side_effect=_raise)
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_BATCH_STOP_ON_MALFORMED_RESPONSE = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        with pytest.raises(MalformedCrmBatchResponse):
            await pipe.process_item(_norm(), MagicMock())


@pytest.mark.asyncio
async def test_batch_logs_include_batch_item_applied(caplog: pytest.LogCaptureFixture) -> None:
    t = _transport()
    t.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._transport = t
    pipe._batch_size = 1
    caplog.set_level(logging.INFO)
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 3
        await pipe.process_item(_norm(), MagicMock())
    assert "BATCH_ITEM_APPLIED" in caplog.text
