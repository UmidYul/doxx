from __future__ import annotations

from types import SimpleNamespace

from config import settings as settings_mod

from application.release.rollback_advisor import decide_feature_rollback, decide_store_rollback


def test_feature_rollback_on_domain_critical(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_AUTO_ROLLBACK_ADVICE", True)
    alerts = [SimpleNamespace(severity="critical", domain="normalization", store_name=None)]
    d = decide_feature_rollback("typed_specs_mapping", SimpleNamespace(status="healthy"), alerts)
    assert d.should_rollback is True
    assert d.target_scope == "feature"


def test_store_rollback_on_store_critical(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_AUTO_ROLLBACK_ADVICE", True)
    alerts = [SimpleNamespace(severity="critical", domain="store_access", store_name="shop1", alert_code="X")]
    d = decide_store_rollback("shop1", SimpleNamespace(status="degraded"), alerts)
    assert d.should_rollback is True
    assert d.target_scope == "store"
