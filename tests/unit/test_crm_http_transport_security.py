from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from domain.security import SecurityValidationResult
from infrastructure.transports.crm_http import CrmHttpTransport


@pytest.mark.asyncio
async def test_ensure_client_uses_loaded_parser_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.transports.crm_http as ch

    monkeypatch.setattr(ch.settings, "CRM_PARSER_KEY", "p" * 24)
    monkeypatch.setattr(ch.settings, "CRM_BASE_URL", "http://crm.test")
    monkeypatch.setattr(ch.settings, "CRM_HTTP_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(ch.settings, "CRM_PARSER_KEY_FILE", "")
    monkeypatch.setattr(ch.settings, "ENABLE_SECRET_FILE_FALLBACK", True)
    monkeypatch.setattr(ch.settings, "SECURITY_MODE", "baseline")
    monkeypatch.setattr(ch.settings, "SECURITY_FAIL_FAST_ON_INVALID_CONFIG", True)

    ok = SecurityValidationResult(passed=True, mode="baseline", errors=[], warnings=[], notes=[])

    with patch.object(ch, "run_startup_security_checks", return_value=ok):
        with patch.object(ch.httpx, "AsyncClient") as AC:
            mock_client = AsyncMock()
            mock_client.base_url = "http://crm.test/"
            AC.return_value = mock_client
            t = CrmHttpTransport()
            await t._ensure_client()

    AC.assert_called_once()
    headers = AC.call_args.kwargs["headers"]
    assert headers["X-Parser-Key"] == "p" * 24
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_request_merges_signing_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.transports.crm_http as ch

    monkeypatch.setattr(ch.settings, "CRM_PARSER_KEY", "p" * 24)
    monkeypatch.setattr(ch.settings, "CRM_BASE_URL", "http://crm.test")
    monkeypatch.setattr(ch.settings, "CRM_HTTP_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(ch.settings, "CRM_HTTP_RETRY_ATTEMPTS", 0)
    monkeypatch.setattr(ch.settings, "CRM_HTTP_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(ch.settings, "CRM_SYNC_ENDPOINT", "/api/parser/sync")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_INTEGRITY_MODE", "hmac_optional")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_SIGNING_SECRET", "signing-secret-32-chars-minimum!!")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_SIGNING_SECRET_FILE", "")
    monkeypatch.setattr(ch.settings, "ENABLE_SECRET_FILE_FALLBACK", True)
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_TIMESTAMP_HEADER", "X-Request-Timestamp")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_NONCE_HEADER", "X-Request-Nonce")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_SIGNATURE_HEADER", "X-Request-Signature")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_SIGNATURE_ALGORITHM", "hmac-sha256")

    ok = SecurityValidationResult(passed=True, mode="baseline", errors=[], warnings=[], notes=[])

    mock_client = AsyncMock()
    mock_client.base_url = "http://crm.test/"
    mock_resp = httpx.Response(
        200,
        content=b"{}",
        request=httpx.Request("POST", "http://crm.test/api/parser/sync"),
    )
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch.object(ch, "run_startup_security_checks", return_value=ok):
        t = CrmHttpTransport()
        t._client = mock_client
        await t._request_with_retry("POST", "/api/parser/sync", b"{}")
        kw = mock_client.request.await_args.kwargs
        hdrs = kw.get("headers") or {}
        assert any("timestamp" in k.lower() for k in hdrs)
        assert any("signature" in k.lower() for k in hdrs)


@pytest.mark.asyncio
async def test_debug_log_does_not_emit_raw_parser_key(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import infrastructure.transports.crm_http as ch

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(ch.settings, "CRM_PARSER_KEY", "SECRETKEY123456789012345678")
    monkeypatch.setattr(ch.settings, "CRM_BASE_URL", "http://crm.test")
    monkeypatch.setattr(ch.settings, "CRM_HTTP_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(ch.settings, "CRM_HTTP_RETRY_ATTEMPTS", 0)
    monkeypatch.setattr(ch.settings, "CRM_SYNC_ENDPOINT", "/sync")
    monkeypatch.setattr(ch.settings, "CRM_REQUEST_INTEGRITY_MODE", "none")

    ok = SecurityValidationResult(passed=True, mode="baseline", errors=[], warnings=[], notes=[])

    mock_client = AsyncMock()
    mock_client.base_url = "http://crm.test/"
    mock_resp = httpx.Response(
        200,
        content=b"{}",
        request=httpx.Request("POST", "http://crm.test/sync"),
    )
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch.object(ch, "run_startup_security_checks", return_value=ok):
        t = CrmHttpTransport()
        t._client = mock_client
        await t._request_with_retry("POST", "/sync", b"{}")

    combined = caplog.text
    assert "SECRETKEY123456789012345678" not in combined
