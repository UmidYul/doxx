from __future__ import annotations

from config.settings import Settings
from infrastructure.security.minimizer import (
    minimize_headers_for_support,
    minimize_payload_for_logging,
    minimize_payload_for_support,
)


def test_minimize_logging_drops_non_loggable() -> None:
    s = Settings(_env_file=None, ENABLE_DATA_MINIMIZATION=True)  # type: ignore[arg-type]
    out = minimize_payload_for_logging(
        {"entity_key": "x", "headers": {"X-Parser-Key": "secret"}, "parser_key": "abc"},
    )
    assert "entity_key" in out
    assert "headers" not in out
    assert "parser_key" not in out


def test_minimize_support_respects_spec_flags() -> None:
    s = Settings(
        _env_file=None,
        ENABLE_DATA_MINIMIZATION=True,
        SUPPORT_EXPORT_INCLUDE_RAW_SPECS=False,
        SUPPORT_EXPORT_INCLUDE_TYPED_SPECS=False,
        SUPPORT_EXPORT_INCLUDE_FIELD_CONFIDENCE=False,
    )  # type: ignore[arg-type]
    out = minimize_payload_for_support(
        {
            "source_id": "1",
            "raw_specs": {"a": "b"},
            "typed_specs": {"c": "d"},
            "field_confidence": {"x": 0.9},
        },
        s,
    )
    assert out.get("source_id") == "1"
    assert "raw_specs" not in out
    assert "typed_specs" not in out
    assert "field_confidence" not in out


def test_minimize_headers_support_disabled() -> None:
    s = Settings(_env_file=None, SUPPORT_EXPORT_INCLUDE_RAW_HEADERS=False)  # type: ignore[arg-type]
    h = minimize_headers_for_support({"Authorization": "bearer x"}, s)
    assert h.get("_omitted") is True
