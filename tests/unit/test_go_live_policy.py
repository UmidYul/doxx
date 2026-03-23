from __future__ import annotations

from config.settings import settings
from domain.production_readiness import ProductionReadinessReport
from domain.release_quality import ReleaseReadinessSummary

from application.go_live.go_live_policy import assess_go_live


def _report(overall: str = "ready") -> ProductionReadinessReport:
    return ProductionReadinessReport(
        overall_status=overall,  # type: ignore[arg-type]
        domains=["crawl"],
        checklist=[],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="prepare_go_live",
    )


def _good_status() -> dict[str, object]:
    return {
        "security_baseline_validated": True,
        "observability_baseline_ok": True,
        "rollout_policy_configured": True,
        "crm_contract_checks_pass": True,
        "lifecycle_compatibility_clean": True,
        "dry_run_passed": True,
        "smoke_passed": True,
        "contract_checks_passed": True,
        "store_acceptance_complete": True,
        "production_config_validated": True,
        "parser_key_security_validated": True,
        "observability_export_ok": True,
        "release_report_reviewed": True,
        "canary_scope_confirmed": True,
    }


def _rollout_canary() -> dict[str, object]:
    return {"stores_by_stage": {"canary": ["s1"], "full": [], "partial": [], "disabled": []}}


def _release_ok() -> ReleaseReadinessSummary:
    return ReleaseReadinessSummary(
        overall_passed=True,
        critical_failures=0,
        checks=[],
        gates=[],
        recommended_action="release",
    )


def _docs_ok() -> dict[str, object]:
    return {"enabled_stores": ["s1"], "missing_playbooks": []}


def test_critical_readiness_blocker_yields_no_go(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    a = assess_go_live(
        _report("blocked"),
        _release_ok(),
        _rollout_canary(),
        _good_status(),
        docs_coverage=_docs_ok(),
    )
    assert a.decision == "no_go"
    assert a.blocking_reasons


def test_ready_canary_rollout_yields_go(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    a = assess_go_live(
        _report("ready"),
        _release_ok(),
        _rollout_canary(),
        _good_status(),
        docs_coverage=_docs_ok(),
    )
    assert a.decision == "go"


def test_no_release_summary_yields_no_go_when_gates_required(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    a = assess_go_live(
        _report("ready"),
        None,
        _rollout_canary(),
        _good_status(),
        docs_coverage=_docs_ok(),
    )
    assert a.decision == "no_go"


def test_rollout_policy_not_required_allows_go(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    monkeypatch.setattr(settings, "GO_LIVE_REQUIRE_ROLLOUT_POLICY", False)
    st = _good_status()
    st["rollout_policy_configured"] = False
    a = assess_go_live(
        _report("ready"),
        _release_ok(),
        _rollout_canary(),
        st,
        docs_coverage=_docs_ok(),
    )
    assert a.decision == "go"


def test_partial_readiness_go_with_constraints(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    monkeypatch.setattr(settings, "GO_LIVE_REQUIRE_READINESS_READY", False)
    a = assess_go_live(
        _report("partial"),
        _release_ok(),
        _rollout_canary(),
        _good_status(),
        docs_coverage=_docs_ok(),
    )
    assert a.decision == "go_with_constraints"
    assert "readiness_overall_partial_document_waiver" in a.constraints


def test_missing_playbooks_blocks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STORE_NAMES", ["s1"])
    a = assess_go_live(
        _report("ready"),
        _release_ok(),
        _rollout_canary(),
        _good_status(),
        docs_coverage={"enabled_stores": ["s1"], "missing_playbooks": ["s1"]},
    )
    assert a.decision == "no_go"
