from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import orjson
import pytest

from domain.crm_lifecycle import CrmIdentityContext
from domain.crm_sync import CrmSyncItem
from domain.parser_event import ParserSyncEvent
import infrastructure.transports.crm_http as crm_http_mod
from config.settings import Settings
from infrastructure.transports.crm_http import CrmHttpTransport

_CRM_ORIGIN = "http://crm.test"


def _crm_test_settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, CRM_BASE_URL=_CRM_ORIGIN, **kwargs)  # type: ignore[arg-type]


def _crm_client_base(mock_client: AsyncMock) -> None:
    mock_client.base_url = f"{_CRM_ORIGIN}/"


def _crm_mock_response(
    status: int = 200,
    json_body: dict | list | None = None,
    headers: dict | None = None,
    *,
    rel_path: str = "/api/parser/sync/batch",
) -> httpx.Response:
    body = orjson.dumps(json_body or {})
    u = f"{_CRM_ORIGIN}{rel_path}"
    return httpx.Response(
        status_code=status,
        content=body,
        headers=headers or {},
        request=httpx.Request("POST", u),
    )


def _make_item(**overrides) -> CrmSyncItem:
    defaults = dict(
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
    defaults.update(overrides)
    return CrmSyncItem(**defaults)


def _make_event(item: CrmSyncItem | None = None, **overrides) -> ParserSyncEvent:
    data = item or _make_item(**overrides)
    identity = CrmIdentityContext(
        entity_key=data.entity_key,
        external_ids=dict(data.external_ids or {}),
        barcode=data.barcode,
        source_name=data.source_name,
        source_url=data.source_url,
        source_id=data.source_id,
    )
    return ParserSyncEvent(
        event_id=str(uuid.uuid4()),
        event_type="product_found",
        identity=identity,
        payload_hash=data.payload_hash,
        data=data,
    )


@pytest.mark.asyncio
async def test_batch_mixed_item_results_preserved() -> None:
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(
        return_value=_crm_mock_response(
            200,
            {
                "results": [
                    {"success": True, "action": "created", "crm_listing_id": "L0"},
                    {"success": False, "error_message": "bad", "retryable": False},
                ]
            },
        )
    )
    _crm_client_base(mock_client)
    transport._client = mock_client
    events = [
        _make_event(_make_item(entity_key="s:0", source_id="0")),
        _make_event(_make_item(entity_key="s:1", source_id="1", payload_hash="sha256:" + "b" * 64)),
    ]
    s = _crm_test_settings(
        CRM_SYNC_BATCH_ENDPOINT="/api/parser/sync/batch",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
        CRM_BATCH_RETRY_ONLY_RETRYABLE_ITEMS=False,
    )
    with patch.object(crm_http_mod, "settings", s):
        batch = await transport.send_batch_events(events)
    assert len(batch.items) == 2
    assert batch.items[0].success is True
    assert batch.items[1].success is False
    assert batch.items[1].status == "rejected"


@pytest.mark.asyncio
async def test_batch_retryable_item_triggers_send_one() -> None:
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    async def _req(method, url, **kwargs):
        u = str(url)
        if "batch" in u:
            return _crm_mock_response(
                200,
                {"results": [{"success": False, "retryable": True, "error_message": "tmp"}]},
            )
        return _crm_mock_response(200, {"success": True, "action": "created", "crm_listing_id": "L1"}, rel_path="/api/parser/sync")

    mock_client.request = AsyncMock(side_effect=_req)
    _crm_client_base(mock_client)
    transport._client = mock_client
    ev = _make_event()
    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_SYNC_BATCH_ENDPOINT="/api/parser/sync/batch",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
        CRM_BATCH_RETRY_ONLY_RETRYABLE_ITEMS=True,
    )
    with patch.object(crm_http_mod, "settings", s):
        batch = await transport.send_batch_events([ev])
    assert batch.items[0].success is True
    assert mock_client.request.await_count == 2
