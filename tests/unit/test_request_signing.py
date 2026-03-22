from __future__ import annotations

import pytest

from config.settings import Settings
from infrastructure.security.request_signing import (
    build_canonical_request_string,
    build_request_security_headers,
    sign_request_hmac,
)


def test_canonical_deterministic() -> None:
    a = build_canonical_request_string("POST", "/api/x", b"{}", "1", "n1")
    b = build_canonical_request_string("POST", "/api/x", b"{}", "1", "n1")
    assert a == b
    assert "POST" in a
    assert "/api/x" in a


def test_hmac_signature_deterministic() -> None:
    c = build_canonical_request_string("GET", "/p", b"body", "t", "n")
    s1 = sign_request_hmac(c, "secret", "hmac-sha256")
    s2 = sign_request_hmac(c, "secret", "hmac-sha256")
    assert s1 == s2
    assert len(s1) == 64


def test_none_mode_no_headers() -> None:
    s = Settings(
        _env_file=None,
        CRM_REQUEST_INTEGRITY_MODE="none",
        CRM_PARSER_KEY="x" * 20,
    )
    h = build_request_security_headers("POST", "/x", b"{}", s)
    assert h == {}


def test_hmac_optional_adds_headers_when_secret_set() -> None:
    s = Settings(
        _env_file=None,
        CRM_REQUEST_INTEGRITY_MODE="hmac_optional",
        CRM_REQUEST_SIGNING_SECRET="signing-secret-32-chars-minimum!!",
        CRM_PARSER_KEY="x" * 20,
        CRM_REQUEST_TIMESTAMP_HEADER="X-Request-Timestamp",
        CRM_REQUEST_NONCE_HEADER="X-Request-Nonce",
        CRM_REQUEST_SIGNATURE_HEADER="X-Request-Signature",
        CRM_REQUEST_SIGNATURE_ALGORITHM="hmac-sha256",
    )
    h = build_request_security_headers("POST", "/path", b"{}", s)
    assert "X-Request-Timestamp" in h or "X-Request-Timestamp".lower() in {k.lower() for k in h}
    assert len(h) == 3
