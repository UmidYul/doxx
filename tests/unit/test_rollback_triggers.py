from __future__ import annotations

from application.go_live.rollback_triggers import evaluate_rollback_triggers, get_default_rollback_triggers


def test_default_catalog_non_empty() -> None:
    assert len(get_default_rollback_triggers()) >= 5


def test_critical_alert_spike_fires_transport_trigger() -> None:
    fired = evaluate_rollback_triggers(
        {"critical_transport_apply_incident": True},
        [],
    )
    codes = {t.trigger_code for t in fired}
    assert "rb.critical_transport_apply" in codes


def test_malformed_rate_fires_trigger() -> None:
    fired = evaluate_rollback_triggers({"malformed_response_rate": 0.99}, [])
    assert any(t.trigger_code == "rb.malformed_response_spike" for t in fired)
