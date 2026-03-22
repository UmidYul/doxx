from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from domain.crm_apply_result import CrmBatchApplyResult
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
async def test_dedupe_same_entity_and_hash_skips_second_item() -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        item = _norm()
        await pipe.process_item(item, MagicMock())
        await pipe.process_item(_norm(), MagicMock())

    assert pipe._metrics.items_deduped_total == 1
    transport.send_batch_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_entity_new_payload_hash_sends_again() -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(price_value=10), MagicMock())
        await pipe.process_item(_norm(price_value=11), MagicMock())

    assert transport.send_batch_events.await_count == 2


@pytest.mark.asyncio
async def test_registry_stores_crm_ids_after_success() -> None:
    transport = _transport()

    async def _mirror(ev):
        return CrmBatchApplyResult(
            items=[
                crm_apply_ok(
                    ev[0],
                    crm_listing_id="L42",
                    crm_product_id="P99",
                    action="updated",
                    status="updated",
                )
            ],
            transport_ok=True,
            http_status=200,
        )

    transport.send_batch_events = AsyncMock(side_effect=_mirror)
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._registry.get_crm_ids("mediapark:1") == ("L42", "P99")


@pytest.mark.asyncio
async def test_partial_batch_success_increments_partial_counter() -> None:
    transport = _transport()

    async def _mixed(ev):
        return CrmBatchApplyResult(
            items=[
                crm_apply_ok(ev[0], crm_listing_id="x", crm_product_id="y"),
                crm_apply_fail(ev[1], retryable=False),
                crm_apply_ok(ev[2], crm_listing_id="a", crm_product_id="b"),
            ],
            transport_ok=True,
            http_status=200,
        )

    transport.send_batch_events = AsyncMock(side_effect=_mixed)
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    pipe._transport = transport
    pipe._batch_size = 3

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        for i in range(3):
            await pipe.process_item(_norm(source_id=str(i)), MagicMock())

    assert pipe._metrics.batch_partial_failures_total == 1
    assert pipe._metrics.items_synced_total == 2
    assert pipe._metrics.items_failed_total == 1


@pytest.mark.asyncio
async def test_retryable_requeued_then_ok_on_next_flush() -> None:
    transport = _transport()
    calls: list[int] = []

    async def _side(ev):
        calls.append(1)
        if len(calls) == 1:
            return CrmBatchApplyResult(
                items=[crm_apply_fail(ev[0], retryable=True, status="retryable_failure")],
                transport_ok=True,
                http_status=200,
            )
        return batch_mirror_success(ev)

    transport.send_batch_events = AsyncMock(side_effect=_side)
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS = True
        s.PARSER_REQUEUE_RETRYABLE_ONCE = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())
        await pipe.close_spider(MagicMock())

    assert transport.send_batch_events.await_count == 2


@pytest.mark.asyncio
async def test_close_spider_flushes_tail_buffer() -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    pipe._transport = transport
    pipe._batch_size = 50

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())
    transport.send_batch_events.assert_not_awaited()

    await pipe.close_spider(MagicMock())
    transport.send_batch_events.assert_awaited_once()
    assert len(transport.send_batch_events.call_args[0][0]) == 1


@pytest.mark.asyncio
async def test_fail_fast_true_on_transport_error() -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=httpx.ReadError("broken"))
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.TRANSPORT_FAIL_FAST = True
        s.SYNC_ALLOW_PARTIAL_BATCH_SUCCESS = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        with pytest.raises(httpx.ReadError):
            await pipe.process_item(_norm(), MagicMock())


@pytest.mark.asyncio
async def test_fail_fast_false_continues_on_transport_error(caplog: pytest.LogCaptureFixture) -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=httpx.ReadError("broken"))
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    caplog.set_level(logging.ERROR)
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.TRANSPORT_FAIL_FAST = False
        s.SYNC_ALLOW_PARTIAL_BATCH_SUCCESS = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())

    assert "transport_error" in caplog.text


@pytest.mark.asyncio
async def test_default_event_type_product_found_logged_in_batch(caplog: pytest.LogCaptureFixture) -> None:
    transport = _transport()
    transport.send_batch_events = AsyncMock(side_effect=lambda ev: batch_mirror_success(ev))
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    caplog.set_level(logging.INFO)
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.PARSER_ENABLE_DELTA_EVENTS = False
        s.MESSAGE_SCHEMA_VERSION = 1
        s.DEFAULT_CURRENCY = "UZS"
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())

    assert "product_found" in caplog.text
    assert "sync_delivery" in caplog.text
