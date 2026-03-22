from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import settings
from infrastructure.pipelines.sync_pipeline import SyncPipeline


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


def _transport_ok(listing: str = "L42", product: str = "P99") -> AsyncMock:
    t = AsyncMock()
    t.close = AsyncMock()

    async def _mirror(ev):
        from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult

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
                    crm_listing_id=listing,
                    crm_product_id=product,
                )
            ],
            transport_ok=True,
            http_status=200,
        )

    t.send_batch_events = AsyncMock(side_effect=_mirror)
    return t


@pytest.mark.asyncio
async def test_product_found_then_price_changed_same_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PARSER_ENABLE_DELTA_EVENTS", True)
    monkeypatch.setattr(settings, "PARSER_ENABLE_RUNTIME_DELTA_EVENTS", True)
    monkeypatch.setattr(settings, "PARSER_ENABLE_PRICE_CHANGED_EVENT", True)
    monkeypatch.setattr(settings, "PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS", True)
    monkeypatch.setattr(settings, "MESSAGE_SCHEMA_VERSION", 1)
    monkeypatch.setattr(settings, "DEFAULT_CURRENCY", "UZS")
    monkeypatch.setattr(settings, "CRM_INCLUDE_SPEC_COVERAGE", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_FIELD_CONFIDENCE", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_NORMALIZATION_QUALITY", False)

    transport = _transport_ok()
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
    first_ev = transport.send_batch_events.call_args_list[0][0][0][0]
    second_ev = transport.send_batch_events.call_args_list[1][0][0][0]
    assert first_ev.event_type == "product_found"
    assert second_ev.event_type == "price_changed"
    assert second_ev.identity.crm_listing_id == "L42"


@pytest.mark.asyncio
async def test_bridge_populated_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MESSAGE_SCHEMA_VERSION", 1)
    monkeypatch.setattr(settings, "DEFAULT_CURRENCY", "UZS")
    monkeypatch.setattr(settings, "CRM_INCLUDE_SPEC_COVERAGE", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_FIELD_CONFIDENCE", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS", False)
    monkeypatch.setattr(settings, "CRM_INCLUDE_NORMALIZATION_QUALITY", False)

    transport = _transport_ok()
    pipe = SyncPipeline()
    pipe._transport = transport
    pipe._batch_size = 1

    with patch("infrastructure.pipelines.sync_pipeline.settings") as s:
        s.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD = False
        s.SYNC_BUFFER_FLUSH_SECONDS = 0.0
        s.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN = 5
        await pipe.process_item(_norm(), MagicMock())
    assert pipe._identity_bridge.has_listing_id("mediapark:1") is True
