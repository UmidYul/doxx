from __future__ import annotations

from config.settings import settings

from application.qa.run_store_acceptance import run_acceptance_for_store
from application.release import rollout_logger as rlog
from application.release.rollout_policy_engine import decide_store_rollout, get_store_rollout_state, is_feature_enabled
from infrastructure.spiders.store_acceptance import get_store_acceptance_profile


def can_store_run(store_name: str, store_status: object | None = None) -> bool:
    """Lightweight gate: rollout + health; does not re-run full acceptance on hot path."""
    key = (store_name or "").strip().lower()
    srs = get_store_rollout_state(key)
    if not srs.enabled:
        rlog.log_store_enablement_decided(store_name=key, allowed=False, stage=srs.stage, reason="store_rollout_disabled")
        return False
    st = str(getattr(store_status, "status", "") or "").lower()
    if st == "failing" and settings.ROLLOUT_BLOCK_ON_FAILING_STATUS:
        rlog.log_store_enablement_decided(store_name=key, allowed=False, stage=srs.stage, reason="operational_status_failing")
        return False
    rlog.log_store_enablement_decided(store_name=key, allowed=True, stage=srs.stage, reason="rollout_and_health_ok")
    return True


def build_store_enablement_summary(store_name: str) -> dict[str, object]:
    key = (store_name or "").strip().lower()
    srs = decide_store_rollout(key)
    prof = get_store_acceptance_profile(key)
    acc_ok: bool | None = None
    if is_feature_enabled("store_acceptance_enforced", key) and key in ("mediapark", "uzum"):
        try:
            report, _ = run_acceptance_for_store(key)
            acc_ok = bool(report.get("quality_gate_passed"))
        except Exception:
            acc_ok = False
    elif is_feature_enabled("store_acceptance_enforced", key):
        acc_ok = None
    return {
        "store_name": key,
        "rollout_stage": srs.stage,
        "rollout_enabled": srs.enabled,
        "canary": srs.canary,
        "acceptance_profile_store": prof.store_name,
        "acceptance_enforced": is_feature_enabled("store_acceptance_enforced", key),
        "acceptance_gate_passed": acc_ok,
        "notes": list(srs.notes),
    }


def explain_store_enablement(store_name: str) -> list[str]:
    s = build_store_enablement_summary(store_name)
    lines = [
        f"store={s['store_name']} rollout_stage={s['rollout_stage']} enabled={s['rollout_enabled']}",
        f"canary={s['canary']} acceptance_enforced={s['acceptance_enforced']} acceptance_passed={s['acceptance_gate_passed']}",
    ]
    lines.extend(str(n) for n in s.get("notes") or [])
    return lines
