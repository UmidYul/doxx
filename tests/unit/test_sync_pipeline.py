from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from infrastructure.pipelines.sync_pipeline import SyncPipeline
from tests.unit.batch_apply_helpers import batch_mirror_success


def _sample_item(**norm_overrides) -> dict:
    norm = {
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
    norm.update(norm_overrides)
    return {"url": "https://mediapark.uz/p/1", "_normalized": norm}


def _mock_transport() -> AsyncMock:
    transport = AsyncMock()

    async def _batch(ev):
        return batch_mirror_success(ev)

    transport.send_batch_events = AsyncMock(side_effect=_batch)
    transport.close = AsyncMock()
    return transport


@pytest.mark.asyncio
async def test_flush_uses_send_batch_events_even_for_single_item():
    pipe = SyncPipeline()
    transport = _mock_transport()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        out = await pipe.process_item(_sample_item(), MagicMock())

    assert out.get("_sync_payload_entity_key") == "mediapark:1"
    transport.send_batch_events.assert_awaited_once()

    batch = transport.send_batch_events.call_args[0][0]
    assert len(batch) == 1
    sync_item = batch[0].data
    assert sync_item.source_name == "mediapark"
    assert sync_item.entity_key == "mediapark:1"
    assert sync_item.price_value == 10
    assert sync_item.sync_mode == "snapshot"
    assert batch[0].event_type == "product_found"


@pytest.mark.asyncio
async def test_skips_without_normalized(caplog: pytest.LogCaptureFixture):
    pipe = SyncPipeline()
    pipe._transport = _mock_transport()

    caplog.set_level(logging.WARNING)
    out = await pipe.process_item({"url": "https://x", "_normalized": None}, MagicMock())
    assert out is not None
    assert "missing_normalized" in caplog.text
    assert "sync_delivery" in caplog.text


@pytest.mark.asyncio
async def test_uses_send_batch_for_multiple_items():
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    transport = _mock_transport()
    pipe._transport = transport
    pipe._batch_size = 3

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        for i in range(3):
            item = _sample_item(source_id=str(i))
            await pipe.process_item(item, MagicMock())

    transport.send_batch_events.assert_awaited_once()
    assert len(transport.send_batch_events.call_args[0][0]) == 3


@pytest.mark.asyncio
async def test_batch_size_capped_at_100():
    pipe = SyncPipeline()
    assert pipe._batch_size <= 100


@pytest.mark.asyncio
async def test_flush_on_close_spider():
    pipe = SyncPipeline()
    pipe._last_flush_mono = time.monotonic()
    transport = _mock_transport()
    pipe._transport = transport
    pipe._batch_size = 100

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.SYNC_BUFFER_FLUSH_SECONDS = 86400.0
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_sample_item(), MagicMock())

    transport.send_batch_events.assert_not_awaited()

    await pipe.close_spider(MagicMock())

    transport.send_batch_events.assert_awaited_once()
    assert len(transport.send_batch_events.call_args[0][0]) == 1
    transport.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_fast_propagates_transport_error():
    pipe = SyncPipeline()
    transport = _mock_transport()
    transport.send_batch_events = AsyncMock(side_effect=httpx.ConnectError("CRM down"))
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_BATCH_SIZE = 1
        s.TRANSPORT_FAIL_FAST = True
        s.SYNC_ALLOW_PARTIAL_BATCH_SUCCESS = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        with pytest.raises(httpx.ConnectError, match="CRM down"):
            await pipe.process_item(_sample_item(), MagicMock())


@pytest.mark.asyncio
async def test_no_fail_fast_logs_transport_error(caplog: pytest.LogCaptureFixture):
    pipe = SyncPipeline()
    transport = _mock_transport()
    transport.send_batch_events = AsyncMock(side_effect=httpx.ConnectError("CRM down"))
    pipe._transport = transport
    pipe._batch_size = 1

    caplog.set_level(logging.ERROR)
    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_BATCH_SIZE = 1
        s.TRANSPORT_FAIL_FAST = False
        s.SYNC_ALLOW_PARTIAL_BATCH_SUCCESS = True
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_sample_item(), MagicMock())

    assert "transport_error" in caplog.text
