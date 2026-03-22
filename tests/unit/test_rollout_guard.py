from __future__ import annotations

from types import SimpleNamespace

from config import settings as settings_mod

from application.release.rollout_guard import can_promote_stage, should_block_rollout_due_to_health


def test_failing_blocks_rollout(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_ROLLOUT_GUARD_BY_STATUS", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_BLOCK_ON_FAILING_STATUS", True)
    assert should_block_rollout_due_to_health(SimpleNamespace(status="failing"), None) is True


def test_degraded_blocks_promotion(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_ROLLOUT_GUARD_BY_STATUS", True)
    assert can_promote_stage("partial", SimpleNamespace(status="degraded")) is False


def test_healthy_allows_promotion(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_ROLLOUT_GUARD_BY_STATUS", True)
    assert can_promote_stage("partial", SimpleNamespace(status="healthy")) is True
