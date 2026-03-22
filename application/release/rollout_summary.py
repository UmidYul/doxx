from __future__ import annotations

from config.feature_flags import FEATURE_FLAG_REGISTRY
from domain.rollout_policy import FeatureFlagState, RollbackDecision, StoreRolloutState


def build_rollout_summary(
    feature_flags: list[FeatureFlagState],
    store_states: list[StoreRolloutState],
    statuses: dict[str, object] | None,
    rollbacks: list[RollbackDecision],
) -> dict[str, object]:
    _ = statuses
    by_stage: dict[str, list[str]] = {"disabled": [], "canary": [], "partial": [], "full": []}
    for fs in feature_flags:
        by_stage.setdefault(fs.stage, []).append(fs.feature_name)
    stores_by_stage: dict[str, list[str]] = {"disabled": [], "canary": [], "partial": [], "full": []}
    for ss in store_states:
        stores_by_stage.setdefault(ss.stage, []).append(ss.store_name)
    rb = [r.model_dump(mode="json") for r in rollbacks if r.should_rollback]
    return {
        "features_by_stage": by_stage,
        "stores_by_stage": stores_by_stage,
        "rollback_recommendations": rb,
        "registered_features": sorted(FEATURE_FLAG_REGISTRY.keys()),
    }


def build_human_rollout_summary(
    feature_flags: list[FeatureFlagState],
    store_states: list[StoreRolloutState],
    statuses: dict[str, object] | None,
    rollbacks: list[RollbackDecision],
) -> str:
    s = build_rollout_summary(feature_flags, store_states, statuses, rollbacks)
    lines = [
        "Rollout snapshot:",
        f"  features per stage: {s['features_by_stage']}",
        f"  stores per stage: {s['stores_by_stage']}",
    ]
    if s["rollback_recommendations"]:
        lines.append(f"  rollback advice: {s['rollback_recommendations']}")
    return "\n".join(lines)
