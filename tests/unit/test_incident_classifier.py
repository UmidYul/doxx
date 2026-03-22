from __future__ import annotations

from config import settings as settings_mod

from domain.operational_policy import AlertSignal, RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.incident_classifier import (
    classify_run_incident,
    classify_store_incident,
    should_disable_store,
    should_fail_run,
)


def _ss(name: str, **kwargs) -> StoreOperationalStatus:
    return StoreOperationalStatus(store_name=name, **kwargs)


def test_classify_store_prefers_critical_domain():
    st = _ss(
        "s",
        status="failing",
        alerts=[
            AlertSignal(
                alert_code="x",
                severity="critical",
                domain="store_access",
                run_id="r",
                message="m",
            ),
            AlertSignal(
                alert_code="y",
                severity="warning",
                domain="crm_apply",
                run_id="r",
                message="m2",
            ),
        ],
    )
    assert classify_store_incident(st) == "store_access"


def test_classify_run_uses_global_alerts():
    run = RunOperationalStatus(
        run_id="r",
        status="degraded",
        store_statuses=[_ss("a", status="healthy", alerts=[])],
        global_alerts=[
            AlertSignal(
                alert_code="g",
                severity="high",
                domain="delivery_transport",
                run_id="r",
                message="sys",
            )
        ],
    )
    assert classify_run_incident(run) == "delivery_transport"


def test_should_disable_store_respects_setting(monkeypatch):
    st = _ss(
        "s",
        status="failing",
        alerts=[
            AlertSignal(
                alert_code="x",
                severity="critical",
                domain="crm_apply",
                run_id="r",
                message="m",
            )
        ],
    )
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT", False)
    assert should_disable_store(st) is False
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT", True)
    assert should_disable_store(st) is True


def test_should_fail_run_respects_setting(monkeypatch):
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
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT", False)
    assert should_fail_run(run) is False
    monkeypatch.setattr(settings_mod.settings, "INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT", True)
    assert should_fail_run(run) is True
