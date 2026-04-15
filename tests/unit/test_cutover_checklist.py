from __future__ import annotations

from application.go_live.cutover_checklist import build_cutover_checklist, evaluate_cutover_checklist
from domain.production_readiness import ProductionReadinessReport


def _report() -> ProductionReadinessReport:
    return ProductionReadinessReport(
        overall_status="ready",
        domains=["crawl"],
        checklist=[],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="prepare_go_live",
    )


def test_cutover_all_complete_when_statuses_good(monkeypatch) -> None:
    monkeypatch.setattr("application.go_live.cutover_checklist.settings.STORE_NAMES", ["s1"])
    rollout = {"stores_by_stage": {"canary": ["s1"], "full": [], "partial": [], "disabled": []}}
    st = {
        "production_config_validated": True,
        "parser_key_security_validated": True,
        "rollout_scope_confirmed": True,
        "enabled_stores_confirmed": True,
        "dry_run_passed": True,
        "smoke_passed": True,
        "release_report_reviewed": True,
        "canary_scope_confirmed": True,
    }
    items = build_cutover_checklist(_report(), None, rollout, statuses=st)
    ok, blockers = evaluate_cutover_checklist(items)
    assert ok is True
    assert blockers == []


def test_cutover_fails_without_dry_run(monkeypatch) -> None:
    monkeypatch.setattr("application.go_live.cutover_checklist.settings.STORE_NAMES", ["s1"])
    rollout = {"stores_by_stage": {"canary": ["s1"], "full": [], "partial": [], "disabled": []}}
    st = {"canary_scope_confirmed": True}
    items = build_cutover_checklist(_report(), None, rollout, statuses=st)
    ok, blockers = evaluate_cutover_checklist(items)
    assert ok is False
    assert "cutover.dry_run_smoke" in blockers


def test_antiban_enabled_adds_blocking_preflight_and_rollback(monkeypatch) -> None:
    monkeypatch.setattr("application.go_live.cutover_checklist.settings.STORE_NAMES", ["s1"])
    monkeypatch.setattr("application.go_live.cutover_checklist.settings.SCRAPY_RANDOMIZED_DELAY_ENABLED", True)
    rollout = {"stores_by_stage": {"canary": ["s1"], "full": [], "partial": [], "disabled": []}}
    st = {
        "production_config_validated": True,
        "parser_key_security_validated": True,
        "rollout_scope_confirmed": True,
        "enabled_stores_confirmed": True,
        "dry_run_passed": True,
        "smoke_passed": True,
        "release_report_reviewed": True,
        "canary_scope_confirmed": True,
    }
    items = build_cutover_checklist(_report(), None, rollout, statuses=st)
    ok, blockers = evaluate_cutover_checklist(items)
    assert ok is False
    assert "cutover.antiban_rollout_preflight" in blockers
    assert "cutover.antiban_rollback_drill" in blockers
