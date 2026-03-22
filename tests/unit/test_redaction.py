from __future__ import annotations

import pytest

from infrastructure.security import redaction as R


def test_redact_headers_masks_parser_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R.settings, "MASK_SENSITIVE_HEADERS_IN_LOGS", True)
    out = R.redact_headers({"X-Parser-Key": "secret", "X-Request-Signature": "sig", "Accept": "json"})
    assert out["X-Parser-Key"] == "[REDACTED]"
    assert out["X-Request-Signature"] == "[REDACTED]"
    assert out["Accept"] == "json"


def test_redact_payload_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R.settings, "MASK_SENSITIVE_FIELDS_IN_LOGS", True)
    out = R.redact_payload({"api_key": "x", "entity_key": "ok", "nested": {"password": "p"}})
    assert out["api_key"] == "[REDACTED]"
    assert out["entity_key"] == "ok"
    assert out["nested"]["password"] == "[REDACTED]"


def test_redact_url_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R.settings, "MASK_SENSITIVE_HEADERS_IN_LOGS", True)
    u = R.redact_url("https://x.example/api?token=abc&foo=1")
    assert "REDACTED" in u
    assert "foo=1" in u


def test_redact_exception_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R.settings, "MASK_SENSITIVE_FIELDS_IN_LOGS", True)
    m = R.redact_exception_message('error X-Parser-Key: supersecret trailing')
    assert "supersecret" not in m or "[REDACTED]" in m
