from __future__ import annotations

import pytest

from application.release.migration_readiness import (
    build_migration_readiness_report,
    summarize_migration_risk,
)
from domain.compatibility import CompatibilityReport, ContractChange, DeprecationNotice, MigrationPlan


def test_migration_readiness_blocks_on_unsafe_breaking(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.migration_readiness as mr

    monkeypatch.setattr(mr.settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False)
    reports = [
        CompatibilityReport(
            surface="crm_payload",
            compatible=False,
            compatibility_level="breaking",
            breaking_changes=[
                ContractChange(
                    surface="crm_payload",
                    change_name="removed_field:x",
                    change_type="breaking",
                    compatibility_level="breaking",
                    affected_fields=["x"],
                )
            ],
            conditional_changes=[],
            additive_changes=[],
        )
    ]
    doc = build_migration_readiness_report(reports, [], [])
    assert doc["block_release_recommended"] is True
    assert doc["release_recommendation"] == "block_release"
    s = summarize_migration_risk(reports, [], [])
    assert "block_release" in s


def test_safe_additive_ship(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.migration_readiness as mr

    monkeypatch.setattr(mr.settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False)
    reports = [
        CompatibilityReport(
            surface="crm_payload",
            compatible=True,
            compatibility_level="backward_compatible",
            breaking_changes=[],
            conditional_changes=[],
            additive_changes=[],
        )
    ]
    doc = build_migration_readiness_report(reports, [], [])
    assert doc["block_release_recommended"] is False
    assert doc["release_recommendation"] in ("ship", "staged_rollout")


def test_deprecations_listed() -> None:
    dep = DeprecationNotice(
        surface="crm_payload",
        field_name="f",
        status="deprecated",
        replacement_field="g",
        deprecation_reason="r",
    )
    doc = build_migration_readiness_report([], [], [dep])
    assert any("crm_payload:f" in x for x in doc["deprecated_fields_tracked"])  # type: ignore[arg-type]
