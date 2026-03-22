from __future__ import annotations

from config import settings as settings_mod

from domain.operational_policy import AlertSignal, RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.store_control import (
    explain_run_action,
    suggest_run_action,
    suggest_store_action,
)


def test_suggest_store_disable_only_when_severe_and_policy(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT", False)
    st = StoreOperationalStatus(
        store_name="s",
        status="failing",
        alerts=[
            AlertSignal(
                alert_code="c",
                severity="critical",
                domain="store_access",
                run_id="r",
                message="blocked",
            )
        ],
    )
    assert suggest_store_action(st) == "degrade"
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT", True)
    assert suggest_store_action(st) == "disable_store"


def test_suggest_run_fail_only_when_policy(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT", False)
    run = RunOperationalStatus(
        run_id="r",
        status="failing",
        store_statuses=[],
        global_alerts=[
            AlertSignal(
                alert_code="g",
                severity="critical",
                domain="internal",
                run_id="r",
                message="x",
            )
        ],
    )
    assert suggest_run_action(run) == "degrade"
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT", True)
    assert suggest_run_action(run) == "fail_run"


def test_explain_run_action_advisory_default():
    run = RunOperationalStatus(run_id="r", status="healthy", store_statuses=[], global_alerts=[])
    lines = explain_run_action(run)
    assert any("advisory" in x for x in lines)
