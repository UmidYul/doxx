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
from infrastructure.transports.crm_http import CrmBusinessError, CrmHttpTransport

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
    rel_path: str = "/api/parser/sync",
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


def _ok_row(**extra):
    return {"success": True, "crm_product_id": "p1", "crm_listing_id": "l1", "action": "created", **extra}


# ---- success ----


@pytest.mark.asyncio
async def test_send_one_event_success():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(return_value=_crm_mock_response(200, _ok_row()))
    _crm_client_base(mock_client)
    transport._client = mock_client

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        result = await transport.send_one_event(_make_event())

    assert result.success is True
    assert result.crm_product_id == "p1"
    assert result.crm_listing_id == "l1"
    assert result.action == "created"
    mock_client.request.assert_awaited_once()


# ---- 429 retry ----


@pytest.mark.asyncio
async def test_retries_on_429():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(
        side_effect=[
            _crm_mock_response(429, headers={"Retry-After": "0"}),
            _crm_mock_response(200, _ok_row(action="created")),
        ]
    )
    _crm_client_base(mock_client)
    transport._client = mock_client

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=3,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        result = await transport.send_one_event(_make_event())

    assert result.success is True
    assert result.action == "created"
    assert mock_client.request.await_count == 2


# ---- 500 retry ----


@pytest.mark.asyncio
async def test_retries_on_500():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(
        side_effect=[
            _crm_mock_response(500),
            _crm_mock_response(200, _ok_row(action="updated")),
        ]
    )
    _crm_client_base(mock_client)
    transport._client = mock_client

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=3,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        result = await transport.send_one_event(_make_event())

    assert result.success is True
    assert result.action == "updated"
    assert mock_client.request.await_count == 2


# ---- 400 no retry (SyncDeliveryResult, not raised) ----


@pytest.mark.asyncio
async def test_no_retry_on_400_returns_failed_result():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(return_value=_crm_mock_response(400, {"error": "bad request"}))
    _crm_client_base(mock_client)
    transport._client = mock_client

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=3,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        result = await transport.send_one_event(_make_event())

    assert result.success is False
    assert result.retryable is False
    assert result.http_status == 400
    assert mock_client.request.await_count == 1


@pytest.mark.asyncio
async def test_no_retry_on_401_403_422():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    transport._client = mock_client

    _crm_client_base(mock_client)
    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=3,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        for code in (401, 403, 422):
            mock_client.request = AsyncMock(return_value=_crm_mock_response(code, {"detail": "nope"}))
            r = await transport.send_one_event(_make_event())
            assert r.success is False
            assert r.retryable is False
            assert r.http_status == code


# ---- batch fallback on 404 / 501 ----


@pytest.mark.asyncio
async def test_batch_fallback_on_404():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    async def _side_effect(method, url, **kwargs):
        if "batch" in str(url):
            return _crm_mock_response(404, rel_path="/api/parser/sync/batch")
        return _crm_mock_response(200, _ok_row())

    mock_client.request = AsyncMock(side_effect=_side_effect)
    _crm_client_base(mock_client)
    transport._client = mock_client

    events = [_make_event(_make_item(entity_key=f"s:{i}", source_id=str(i))) for i in range(3)]

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_SYNC_BATCH_ENDPOINT="/api/parser/sync/batch",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        batch = await transport.send_batch_events(events)

    assert transport._batch_supported is False
    assert len(batch.items) == 3
    assert all(r.success and r.action == "created" for r in batch.items)


@pytest.mark.asyncio
async def test_batch_fallback_on_501():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    async def _side_effect(method, url, **kwargs):
        if "batch" in str(url):
            return _crm_mock_response(501, rel_path="/api/parser/sync/batch")
        return _crm_mock_response(200, _ok_row())

    mock_client.request = AsyncMock(side_effect=_side_effect)
    _crm_client_base(mock_client)
    transport._client = mock_client

    events = [_make_event(_make_item(entity_key=f"x:{i}", source_id=str(i))) for i in range(2)]

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_SYNC_BATCH_ENDPOINT="/api/parser/sync/batch",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        batch = await transport.send_batch_events(events)

    assert transport._batch_supported is False
    assert len(batch.items) == 2
    assert all(r.success for r in batch.items)


# ---- batch size enforcement ----


def test_batch_size_capped():
    from config.settings import Settings

    with pytest.raises(Exception):
        Settings(CRM_BATCH_SIZE=101, _env_file=None)


# ---- transport error retry ----


@pytest.mark.asyncio
async def test_retries_on_transport_error():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            _crm_mock_response(200, _ok_row()),
        ]
    )
    _crm_client_base(mock_client)
    transport._client = mock_client

    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=3,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        result = await transport.send_one_event(_make_event())

    assert result.success is True
    assert result.action == "created"
    assert mock_client.request.await_count == 2


# ---- orjson serialization (envelope + data) ----


@pytest.mark.asyncio
async def test_sends_orjson_body_with_parser_event_envelope():
    transport = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(return_value=_crm_mock_response(200, _ok_row()))
    _crm_client_base(mock_client)
    transport._client = mock_client

    item = _make_item()
    ev = _make_event(item)
    s = _crm_test_settings(
        CRM_SYNC_ENDPOINT="/api/parser/sync",
        CRM_HTTP_RETRY_ATTEMPTS=0,
        CRM_HTTP_RETRY_BACKOFF_SECONDS=0.0,
    )
    with patch.object(crm_http_mod, "settings", s):
        await transport.send_one_event(ev)

    call_kwargs = mock_client.request.call_args.kwargs
    body = call_kwargs.get("content")
    parsed = orjson.loads(body)
    assert parsed["event_id"] == ev.event_id
    assert parsed["event_type"] == "product_found"
    assert "sent_at" in parsed
    assert parsed["data"]["entity_key"] == "mediapark:1"
    assert parsed["data"]["sync_mode"] == "snapshot"
    assert parsed["data"]["source_name"] == "mediapark"


# ---- CrmBusinessError still usable for callers that catch it ----


def test_crm_business_error_attrs():
    exc = CrmBusinessError(400, "bad")
    assert exc.status == 400
    assert "400" in str(exc)
