from __future__ import annotations

import pytest

from application.release.deprecation_registry import (
    clear_deprecation_registry_for_tests,
    register_deprecation_notice,
)
from application.release.shape_compat import (
    apply_export_compatibility,
    apply_shadow_fields,
    build_dual_shape_payload,
    strip_removed_fields,
)
from domain.compatibility import DeprecationNotice


@pytest.fixture(autouse=True)
def _clear_reg() -> None:
    clear_deprecation_registry_for_tests()
    yield
    clear_deprecation_registry_for_tests()


def test_dual_shape_includes_primary_and_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.shape_compat as sc

    monkeypatch.setattr(sc.settings, "ENABLE_DUAL_SHAPE_OUTPUTS", True)
    monkeypatch.setattr(sc.settings, "ENABLE_SHADOW_FIELDS", True)
    register_deprecation_notice(
        DeprecationNotice(
            surface="crm_payload",
            field_name="legacy_title",
            status="shadow",
            replacement_field="title",
            deprecation_reason="rename",
        )
    )
    payload = {"title": "Hello"}
    out = build_dual_shape_payload("crm_payload", payload)
    assert "primary" in out and "legacy_shape" in out
    prim = out["primary"]
    assert isinstance(prim, dict)
    assert prim.get("legacy_title") == "Hello"


def test_deprecation_warnings_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.shape_compat as sc

    monkeypatch.setattr(sc.settings, "ENABLE_DUAL_SHAPE_OUTPUTS", False)
    monkeypatch.setattr(sc.settings, "ENABLE_DEPRECATION_WARNINGS", True)
    register_deprecation_notice(
        DeprecationNotice(
            surface="crm_payload",
            field_name="old_flag",
            status="deprecated",
            replacement_field="new_flag",
            deprecation_reason="cleanup",
        )
    )
    out = apply_export_compatibility("crm_payload", {"old_flag": True})
    assert "old_flag" in out


def test_strip_removed_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.shape_compat as sc

    monkeypatch.setattr(sc.settings, "ENABLE_COMPATIBILITY_GUARDS", True)
    register_deprecation_notice(
        DeprecationNotice(
            surface="diagnostic_snapshot",
            field_name="gone",
            status="removed",
            replacement_field=None,
            deprecation_reason="deleted",
        )
    )
    out = strip_removed_fields("diagnostic_snapshot", {"gone": 1, "keep": 2})
    assert "gone" not in out
    assert out.get("keep") == 2


def test_apply_shadow_fields_fills_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.shape_compat as sc

    monkeypatch.setattr(sc.settings, "ENABLE_SHADOW_FIELDS", True)
    register_deprecation_notice(
        DeprecationNotice(
            surface="crm_payload",
            field_name="legacy_x",
            status="shadow",
            replacement_field="x",
            deprecation_reason="rename",
        )
    )
    out = apply_shadow_fields("crm_payload", {"x": 42})
    assert out["legacy_x"] == 42
