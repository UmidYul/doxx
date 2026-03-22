from __future__ import annotations

from unittest.mock import patch

from application.readiness.phase_policy import can_enter_phase, can_exit_phase
from domain.production_readiness import ProductionReadinessReport, ReadinessChecklistItem


def _chk(
    domain: str,
    item_code: str,
    status: str,
    *,
    required: bool = True,
    risk: str = "medium",
) -> ReadinessChecklistItem:
    return ReadinessChecklistItem(
        domain=domain,  # type: ignore[arg-type]
        item_code=item_code,
        title=item_code,
        description="d",
        required=required,
        status=status,  # type: ignore[arg-type]
        risk_if_missing=risk,  # type: ignore[arg-type]
    )


def test_foundation_always_enter() -> None:
    rep = ProductionReadinessReport(
        overall_status="blocked",
        domains=["crawl"],
        checklist=[_chk("crawl", "c1", "blocked")],
        gaps=[],
        evidence=[],
        blocking_gaps_count=5,
        critical_risk_count=2,
        recommended_action="fix_blockers",
    )
    assert can_enter_phase("foundation", rep) is True


def test_go_live_baseline_entry_blocked_when_crawl_not_ready() -> None:
    rep = ProductionReadinessReport(
        overall_status="partial",
        domains=["crawl", "crm_integration", "security"],
        checklist=[
            _chk("crawl", "c1", "not_started"),
            _chk("crm_integration", "cr1", "ready"),
            _chk("security", "s1", "ready"),
        ],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="continue_build",
    )
    assert can_enter_phase("go_live_baseline", rep) is False


def test_go_live_baseline_entry_allowed_when_core_partial_and_no_blockers() -> None:
    rep = ProductionReadinessReport(
        overall_status="partial",
        domains=["crawl", "crm_integration", "security"],
        checklist=[
            _chk("crawl", "c1", "partial"),
            _chk("crm_integration", "cr1", "partial"),
            _chk("security", "s1", "ready"),
        ],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="continue_build",
    )
    assert can_enter_phase("go_live_baseline", rep) is True


def test_foundation_exit_blocked_until_core_ready() -> None:
    rep = ProductionReadinessReport(
        overall_status="partial",
        domains=["crawl", "crm_integration", "security"],
        checklist=[
            _chk("crawl", "c1", "ready"),
            _chk("crm_integration", "cr1", "partial"),
            _chk("security", "s1", "ready"),
        ],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="continue_build",
    )
    assert can_exit_phase("foundation", rep) is False


def test_phase_entry_emits_log_when_blocked() -> None:
    rep = ProductionReadinessReport(
        overall_status="partial",
        domains=["crawl", "crm_integration", "security"],
        checklist=[
            _chk("crawl", "c1", "not_started"),
            _chk("crm_integration", "cr1", "ready"),
            _chk("security", "s1", "ready"),
        ],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="continue_build",
    )
    with patch("infrastructure.observability.event_logger.log_roadmap_event") as log_fn:
        can_enter_phase("go_live_baseline", rep, emit_structured_logs=True)
        assert log_fn.called


def test_phase_exit_emits_log_when_approved() -> None:
    checklist = [
        _chk("crawl", "c1", "ready"),
        _chk("crm_integration", "cr1", "ready"),
        _chk("security", "s1", "ready"),
        _chk("lifecycle", "l1", "ready"),
        _chk("batch_apply", "b1", "ready"),
        _chk("replay_reconciliation", "r1", "ready"),
        _chk("observability", "o1", "ready"),
        _chk("release_governance", "g1", "ready"),
        _chk("documentation", "d1", "ready"),
    ]
    domains = sorted({c.domain for c in checklist})
    rep = ProductionReadinessReport(
        overall_status="ready",
        domains=domains,
        checklist=checklist,
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="prepare_go_live",
    )
    with patch("infrastructure.observability.event_logger.log_roadmap_event") as log_fn:
        assert can_exit_phase("go_live_baseline", rep, emit_structured_logs=True) is True
        assert log_fn.called
