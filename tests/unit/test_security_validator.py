from __future__ import annotations

import pytest

from config.settings import Settings
from infrastructure.security.security_validator import (
    validate_integrity_settings,
    validate_parser_key,
    validate_security_settings,
)


def _s(**kwargs: object) -> Settings:
    base = dict(
        CRM_PARSER_KEY="x" * 24,
        CRM_PARSER_KEY_FILE="",
        ENABLE_SECRET_FILE_FALLBACK=True,
        CRM_REQUEST_INTEGRITY_MODE="none",
        CRM_REQUEST_SIGNING_SECRET="",
        CRM_REQUEST_SIGNING_SECRET_FILE="",
        CRM_REQUEST_TIMESTAMP_HEADER="X-Request-Timestamp",
        CRM_REQUEST_NONCE_HEADER="X-Request-Nonce",
        CRM_REQUEST_SIGNATURE_HEADER="X-Request-Signature",
        CRM_REQUEST_SIGNATURE_ALGORITHM="hmac-sha256",
        TRANSPORT_TYPE="crm_http",
        CRM_BASE_URL="http://localhost",
    )
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_missing_parser_key_fails() -> None:
    s = _s(CRM_PARSER_KEY="", CRM_PARSER_KEY_FILE="")
    errs = validate_parser_key(s)
    assert errs


def test_hmac_required_without_signing_secret_fails() -> None:
    s = _s(CRM_REQUEST_INTEGRITY_MODE="hmac_required", CRM_REQUEST_SIGNING_SECRET="", CRM_REQUEST_SIGNING_SECRET_FILE="")
    errs = validate_integrity_settings(s)
    assert any("hmac_required" in e.lower() for e in errs)


def test_empty_header_name_fails() -> None:
    s = _s(CRM_REQUEST_INTEGRITY_MODE="hmac_optional", CRM_REQUEST_TIMESTAMP_HEADER="  ")
    errs = validate_integrity_settings(s)
    assert any("TIMESTAMP" in e for e in errs)


def test_validate_security_settings_passes() -> None:
    s = _s()
    r = validate_security_settings(s)
    assert r.passed


def test_short_inline_parser_key_error() -> None:
    s = _s(CRM_PARSER_KEY="short")
    errs = validate_parser_key(s)
    assert any("short" in e.lower() or "minimum" in e.lower() for e in errs)
