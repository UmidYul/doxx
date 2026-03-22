from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from config.settings import Settings
from infrastructure.transports.crm_http import CrmBusinessError, CrmHttpTransport


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, CRM_BASE_URL="http://crm.test", **kwargs)  # type: ignore[arg-type]


def test_validate_response_blocks_redirect_off_crm_host(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.transports.crm_http as ch

    monkeypatch.setattr(ch, "settings", _s())
    t = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.base_url = "http://crm.test/"
    t._client = mock_client

    first = httpx.Request("POST", "http://crm.test/api/parser/sync")
    hop = httpx.Response(302, headers={"Location": "http://attacker.example/hook"}, request=first)
    final_req = httpx.Request("POST", "http://attacker.example/hook")
    resp = httpx.Response(200, content=b"{}", request=final_req, history=[hop])

    with pytest.raises(CrmBusinessError, match="redirect blocked"):
        t._validate_crm_http_response("/api/parser/sync", resp)


def test_validate_response_allows_intra_crm_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.transports.crm_http as ch

    monkeypatch.setattr(ch, "settings", _s())
    t = CrmHttpTransport()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.base_url = "http://crm.test/"
    t._client = mock_client

    first = httpx.Request("POST", "http://crm.test/api/parser/sync")
    hop = httpx.Response(302, headers={"Location": "/api/parser/sync/alt"}, request=first)
    final_req = httpx.Request("POST", "http://crm.test/api/parser/sync/alt")
    resp = httpx.Response(200, content=b"{}", request=final_req, history=[hop])
    t._validate_crm_http_response("/api/parser/sync", resp)
