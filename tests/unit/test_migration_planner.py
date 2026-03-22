from __future__ import annotations

from application.release.migration_planner import (
    build_migration_plan,
    can_use_dual_shape,
    can_use_shadow_mode,
    explain_migration_steps,
)
from domain.compatibility import CompatibilityReport, ContractChange


def test_additive_only_plan() -> None:
    rep = CompatibilityReport(
        surface="crm_payload",
        compatible=True,
        compatibility_level="backward_compatible",
        breaking_changes=[],
        conditional_changes=[],
        additive_changes=[
            ContractChange(
                surface="crm_payload",
                change_name="added_field:x",
                change_type="additive",
                compatibility_level="backward_compatible",
                affected_fields=["x"],
            )
        ],
    )
    plan = build_migration_plan("crm_payload", "v1", "v2", rep)
    assert not plan.can_dual_write
    assert "No hard migration" in plan.required_steps[0]
    steps = explain_migration_steps(plan)
    assert any("dual_write_recommended=False" in s for s in steps)


def test_breaking_suggests_dual_and_shadow() -> None:
    rep = CompatibilityReport(
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
    assert can_use_dual_shape(rep)
    assert can_use_shadow_mode(rep)
    plan = build_migration_plan("crm_payload", "v1", "v2", rep)
    assert plan.can_dual_write
    assert plan.can_shadow_mode
