from __future__ import annotations

from domain.rollout_policy import FeatureFlagState, RollbackDecision, StoreRolloutState

from application.release.rollout_summary import build_human_rollout_summary, build_rollout_summary


def test_build_rollout_summary_shape():
    ff = [FeatureFlagState(feature_name="f1", stage="canary", enabled=True, rollout_percentage=10)]
    ss = [StoreRolloutState(store_name="s1", enabled=True, stage="full")]
    rb = [RollbackDecision(should_rollback=True, target_scope="feature", reason="r", recommended_stage="canary")]
    d = build_rollout_summary(ff, ss, None, rb)
    assert "canary" in d["features_by_stage"]
    assert d["rollback_recommendations"]

def test_human_summary_non_empty():
    text = build_human_rollout_summary([], [], None, [])
    assert "Rollout" in text
