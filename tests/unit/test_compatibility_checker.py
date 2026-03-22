from __future__ import annotations

import pytest

from application.release.compatibility_checker import (
    check_all_core_surfaces,
    check_surface_compatibility,
    should_block_due_to_compatibility,
)


def test_check_surface_additive_compatible() -> None:
    base = {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1}
    cur = dict(base)
    cur["extra"] = 1
    r = check_surface_compatibility("crm_payload", base, cur)
    assert r.compatible
    assert not r.breaking_changes


def test_should_block_on_breaking(monkeypatch: pytest.MonkeyPatch) -> None:
    import application.release.compatibility_checker as cc

    monkeypatch.setattr(cc.settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False)
    from domain.compatibility import CompatibilityReport

    reports = [
        CompatibilityReport(
            surface="crm_payload",
            compatible=False,
            compatibility_level="breaking",
            breaking_changes=[],
            conditional_changes=[],
            additive_changes=[],
        )
    ]
    assert should_block_due_to_compatibility(reports) is True


def test_check_all_core_surfaces_partial() -> None:
    fixtures_ok = {
        "crm_payload": (
            {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1},
            {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1, "x": 1},
        ),
    }
    reps = check_all_core_surfaces(fixtures_ok)
    assert len(reps) >= 1
