from __future__ import annotations

from config.settings import Settings
from infrastructure.security.support_scope_guard import (
    decide_support_export_scope,
    should_include_field,
    should_include_section,
)


def test_decide_scope_observability_includes_more() -> None:
    s = Settings(_env_file=None, ENABLE_SUPPORT_SCOPE_RESTRICTIONS=True)  # type: ignore[arg-type]
    d = decide_support_export_scope("observability", s)
    assert d.allowed
    assert "traces" in d.included_sections or "errors" in d.included_sections


def test_should_include_field_respects_excluded() -> None:
    s = Settings(
        _env_file=None,
        ENABLE_SUPPORT_SCOPE_RESTRICTIONS=True,
        SUPPORT_EXPORT_INCLUDE_FIELD_CONFIDENCE=False,
    )  # type: ignore[arg-type]
    assert not should_include_field("field_confidence", "support", s)


def test_should_include_section() -> None:
    s = Settings(_env_file=None)  # type: ignore[arg-type]
    assert should_include_section("summary", "support", s)
