from __future__ import annotations

from types import SimpleNamespace

from config import settings as settings_mod

from application.release.store_enablement import build_store_enablement_summary, can_store_run


def test_disabled_store_cannot_run(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PROGRESSIVE_STORE_ENABLEMENT", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_DISABLED_STORES", ["x"])
    assert can_store_run("x") is False


def test_summary_reflects_canary_stage(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PROGRESSIVE_STORE_ENABLEMENT", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_CANARY_STORES", ["canary_store"])
    s = build_store_enablement_summary("canary_store")
    assert s["rollout_stage"] == "canary"
    assert s["canary"] is True


def test_summary_partial_stage(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PROGRESSIVE_STORE_ENABLEMENT", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_PARTIAL_STORES", ["p_store"])
    s = build_store_enablement_summary("p_store")
    assert s["rollout_stage"] == "partial"
