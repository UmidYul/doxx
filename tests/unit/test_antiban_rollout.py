from __future__ import annotations

from unittest.mock import patch

from application.release.antiban_rollout import (
    anti_ban_feature_flags_registered,
    build_antiban_rollback_actions,
    build_antiban_rollout_strategy,
    is_antiban_runtime_enabled,
)


def test_all_antiban_feature_flags_registered() -> None:
    ok, missing = anti_ban_feature_flags_registered()
    assert ok is True
    assert missing == []


def test_antiban_runtime_enabled_when_any_gate_true(monkeypatch) -> None:
    monkeypatch.setattr(
        "application.release.antiban_rollout.settings.SCRAPY_RANDOMIZED_DELAY_ENABLED",
        True,
    )
    assert is_antiban_runtime_enabled() is True


def test_build_rollout_strategy_has_required_progressive_stages() -> None:
    strategy = build_antiban_rollout_strategy(store_names=["mediapark", "uzum"], pilot_store="mediapark")
    stage_names = [str(s.get("name")) for s in list(strategy.get("stages") or [])]
    assert stage_names == [
        "local",
        "staging",
        "pilot_1_store",
        "pilot_10_percent_stores",
        "full_rollout",
    ]
    assert strategy["pilot_store"] == "mediapark"


def test_rollout_strategy_uses_canary_percentage_from_settings(monkeypatch) -> None:
    monkeypatch.setattr("application.release.antiban_rollout.settings.ROLLOUT_CANARY_PERCENTAGE", 7)
    strategy = build_antiban_rollout_strategy(store_names=["s1"], pilot_store="s1")
    stages = list(strategy.get("stages") or [])
    ten = next(s for s in stages if s.get("name") == "pilot_10_percent_stores")
    assert ten["target_percentage"] == 7


def test_rollback_actions_are_non_empty() -> None:
    actions = build_antiban_rollback_actions()
    assert len(actions) >= 4
    assert "rollback" in " ".join(actions).lower()


def test_feature_registry_missing_is_reported() -> None:
    with patch("application.release.antiban_rollout.get_feature_spec", return_value=None):
        ok, missing = anti_ban_feature_flags_registered()
    assert ok is False
    assert "access_delay_jitter" in missing
