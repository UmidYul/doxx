from __future__ import annotations

from config.feature_flags import get_feature_spec
from config.settings import settings
from domain.rollout_policy import FeatureFlagState, RolloutDecision, RolloutStage, StoreRolloutState

from application.release import rollout_logger as rlog
from application.release.canary_selector import build_rollout_key, select_canary_bucket
from application.release.rollout_guard import can_enable_feature_based_on_status, should_block_rollout_due_to_health

_STAGE_RANK: dict[RolloutStage, int] = {"disabled": 0, "canary": 1, "partial": 2, "full": 3}


def _parse_stage(s: str) -> RolloutStage:
    v = (s or "disabled").strip().lower()
    if v in _STAGE_RANK:
        return v  # type: ignore[return-value]
    return "disabled"


def _narrow(a: RolloutStage, b: RolloutStage) -> RolloutStage:
    return a if _STAGE_RANK[a] <= _STAGE_RANK[b] else b


def get_store_rollout_state(store_name: str) -> StoreRolloutState:
    key = (store_name or "").strip().lower()
    if not settings.ENABLE_STORE_ROLLOUT_POLICY or not settings.ENABLE_PROGRESSIVE_STORE_ENABLEMENT:
        return StoreRolloutState(
            store_name=key,
            enabled=True,
            stage="full",
            canary=False,
            notes=["store_rollout_policy_or_progressive_disabled"],
        )
    if key in {s.strip().lower() for s in settings.ROLLOUT_DISABLED_STORES}:
        return StoreRolloutState(
            store_name=key,
            enabled=False,
            stage="disabled",
            canary=False,
            notes=["listed_in_ROLLOUT_DISABLED_STORES"],
        )
    if key in {s.strip().lower() for s in settings.ROLLOUT_CANARY_STORES}:
        return StoreRolloutState(
            store_name=key,
            enabled=True,
            stage="canary",
            canary=True,
            notes=["listed_in_ROLLOUT_CANARY_STORES"],
        )
    if key in {s.strip().lower() for s in settings.ROLLOUT_PARTIAL_STORES}:
        return StoreRolloutState(
            store_name=key,
            enabled=True,
            stage="partial",
            canary=False,
            notes=["listed_in_ROLLOUT_PARTIAL_STORES"],
        )
    return StoreRolloutState(
        store_name=key,
        enabled=True,
        stage="full",
        canary=False,
        notes=["default_full_for_configured_store"],
    )


def get_feature_flag_state(feature_name: str, store_name: str | None = None) -> FeatureFlagState:
    fn = (feature_name or "").strip()
    if not settings.ENABLE_FEATURE_FLAGS:
        return FeatureFlagState(
            feature_name=fn,
            stage="full",
            enabled=True,
            notes=["feature_flags_master_disabled"],
        )
    spec = get_feature_spec(fn)
    if spec is None:
        st = _parse_stage(settings.ROLLOUT_DEFAULT_STAGE)
        return FeatureFlagState(
            feature_name=fn,
            stage=st,
            enabled=st != "disabled",
            rollout_percentage=None,
            allowed_stores=[],
            notes=["unknown_feature_uses_ROLLOUT_DEFAULT_STAGE"],
        )
    ov: RolloutStage = spec.default_stage
    if store_name:
        srs = get_store_rollout_state(store_name)
        if fn in srs.feature_overrides:
            ov = srs.feature_overrides[fn]
    return FeatureFlagState(
        feature_name=fn,
        stage=ov,
        enabled=spec.default_enabled,
        rollout_percentage=settings.ROLLOUT_CANARY_PERCENTAGE if ov == "canary" else settings.ROLLOUT_PARTIAL_PERCENTAGE if ov == "partial" else None,
        allowed_stores=list(spec.allowed_stores),
        notes=list(spec.notes),
    )


def decide_feature_rollout(
    feature_name: str,
    store_name: str | None = None,
    entity_key: str | None = None,
    *,
    store_status: object | None = None,
    run_status: object | None = None,
) -> RolloutDecision:
    if not settings.ENABLE_FEATURE_FLAGS:
        return RolloutDecision(
            feature_name=feature_name,
            store_name=store_name,
            stage="full",
            enabled=True,
            reason="feature_flags_disabled",
            canary_selected=False,
            rollout_scope="global",
        )
    spec = get_feature_spec(feature_name)
    if spec is None and _parse_stage(settings.ROLLOUT_DEFAULT_STAGE) == "disabled":
        return RolloutDecision(
            feature_name=feature_name,
            store_name=store_name,
            stage="disabled",
            enabled=False,
            reason="unknown_feature_and_default_stage_disabled",
            canary_selected=False,
            rollout_scope="feature",
        )

    st_name = (store_name or "").strip() or None
    srs = get_store_rollout_state(st_name) if st_name else None
    if srs and not srs.enabled:
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            reason="store_rollout_disabled",
            canary_selected=False,
            rollout_scope="store",
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            canary_selected=False,
            rollout_percentage=None,
            reason=d.reason,
            rollout_scope="store",
        )
        return d

    fs = get_feature_flag_state(feature_name, st_name)
    if not fs.enabled:
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            reason="feature_flag_disabled_in_registry",
            canary_selected=False,
            rollout_scope="feature",
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            canary_selected=False,
            rollout_percentage=None,
            reason=d.reason,
            rollout_scope="feature",
        )
        return d

    if fs.allowed_stores and st_name and st_name.lower() not in {x.strip().lower() for x in fs.allowed_stores}:
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            reason="store_not_in_feature_allowed_stores",
            canary_selected=False,
            rollout_scope="store_feature",
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            canary_selected=False,
            rollout_percentage=None,
            reason=d.reason,
            rollout_scope="store_feature",
        )
        return d

    feat_stage = fs.stage
    if srs:
        feat_stage = _narrow(feat_stage, srs.stage)

    if should_block_rollout_due_to_health(store_status, run_status) and feat_stage in ("full", "partial"):
        feat_stage = "canary"
        rlog.log_rollout_guard_blocked(
            feature_name=feature_name,
            store_name=st_name,
            reason="health_failing_blocks_wide_rollout",
            status="failing",
        )

    if not can_enable_feature_based_on_status(feature_name, store_status, run_status):
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            reason="rollout_guard_status",
            canary_selected=False,
            rollout_scope="store_feature",
        )
        rlog.log_rollout_guard_blocked(
            feature_name=feature_name,
            store_name=st_name,
            reason=d.reason or "",
            status=str(getattr(store_status, "status", None)),
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            canary_selected=False,
            rollout_percentage=None,
            reason=d.reason,
            rollout_scope="store_feature",
        )
        return d

    if feat_stage == "disabled":
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            reason="effective_stage_disabled",
            canary_selected=False,
            rollout_scope="store_feature",
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="disabled",
            enabled=False,
            canary_selected=False,
            rollout_percentage=None,
            reason=d.reason,
            rollout_scope="store_feature",
        )
        return d

    if feat_stage == "full":
        d = RolloutDecision(
            feature_name=feature_name,
            store_name=st_name,
            stage="full",
            enabled=True,
            reason=None,
            canary_selected=False,
            rollout_scope="store_feature" if st_name else "global",
        )
        rlog.log_feature_rollout_decided(
            feature_name=feature_name,
            store_name=st_name,
            stage="full",
            enabled=True,
            canary_selected=False,
            rollout_percentage=None,
            reason="full_rollout",
            rollout_scope=d.rollout_scope,
        )
        return d

    spec_resolved = get_feature_spec(feature_name)
    if not settings.ENABLE_CANARY_ROLLOUT:
        pct = 100
    elif spec_resolved is not None and not spec_resolved.supports_canary:
        pct = 100
    else:
        pct = settings.ROLLOUT_CANARY_PERCENTAGE if feat_stage == "canary" else settings.ROLLOUT_PARTIAL_PERCENTAGE

    if not settings.ROLLOUT_HASH_BASED_SELECTION:
        pct = 100

    rk = build_rollout_key(st_name or "global", entity_key, feature_name)
    selected = select_canary_bucket(rk, pct)
    rlog.log_canary_bucket_selected(key=rk, percentage=pct, selected=selected)

    d = RolloutDecision(
        feature_name=feature_name,
        store_name=st_name,
        stage=feat_stage,
        enabled=selected,
        reason=None if selected else f"canary_or_partial_bucket_miss pct={pct}",
        canary_selected=selected,
        rollout_percentage=pct,
        rollout_scope="store_feature" if st_name else "feature",
    )
    rlog.log_feature_rollout_decided(
        feature_name=feature_name,
        store_name=st_name,
        stage=feat_stage,
        enabled=selected,
        canary_selected=selected,
        rollout_percentage=pct,
        reason=d.reason or "canary_pass",
        rollout_scope=d.rollout_scope,
    )
    return d


def decide_store_rollout(store_name: str) -> StoreRolloutState:
    return get_store_rollout_state(store_name)


def is_feature_enabled(
    feature_name: str,
    store_name: str | None = None,
    entity_key: str | None = None,
    *,
    store_status: object | None = None,
    run_status: object | None = None,
) -> bool:
    return decide_feature_rollout(
        feature_name,
        store_name,
        entity_key,
        store_status=store_status,
        run_status=run_status,
    ).enabled
