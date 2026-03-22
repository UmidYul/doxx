from __future__ import annotations

from typing import Any

from config.settings import settings
from domain.crm_apply_result import CrmApplyResult
from domain.crm_lifecycle import CrmIdentityContext
from domain.crm_replay import ReconciliationDecision, ReconciliationResult


def decide_reconciliation(
    event_type: str,
    apply_result: CrmApplyResult | None,
    runtime_ids: dict[str, str] | None = None,
) -> ReconciliationDecision:
    """Parser-side policy: when to attempt in-run reconciliation (no local DB)."""
    et = (event_type or "").strip().lower()
    _ = et  # reserved for future per-type policy
    if apply_result is None:
        if settings.PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION:
            return ReconciliationDecision(
                should_reconcile=True,
                reconcile_via="resend_product_found",
                reason="response_lost",
            )
        return ReconciliationDecision(should_reconcile=False, reconcile_via="none", reason=None)

    sig = apply_result.parser_reconciliation_signal
    if sig == "missing_ids" and settings.PARSER_RECONCILE_ON_MISSING_IDS:
        return ReconciliationDecision(
            should_reconcile=True,
            reconcile_via="runtime_ids",
            reason="success_missing_crm_ids",
        )
    if sig == "ambiguous_action" and settings.PARSER_RECONCILE_ON_AMBIGUOUS_RESULT:
        return ReconciliationDecision(
            should_reconcile=True,
            reconcile_via="runtime_ids",
            reason="ambiguous_sync_result",
        )
    if sig == "response_lost" and settings.PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION:
        return ReconciliationDecision(
            should_reconcile=True,
            reconcile_via="resend_product_found",
            reason="response_lost",
        )
    return ReconciliationDecision(should_reconcile=False, reconcile_via="none", reason=None)


def reconcile_missing_ids(
    identity: CrmIdentityContext,
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
    apply_result: CrmApplyResult | None = None,
) -> ReconciliationResult:
    """Merge CRM ids from response row, then runtime bridge; optional catalog (disabled by default)."""
    notes: list[str] = []

    if apply_result and apply_result.success:
        lid = apply_result.crm_listing_id
        pid = apply_result.crm_product_id
        if lid or pid:
            return ReconciliationResult(
                resolved=True,
                crm_listing_id=lid,
                crm_product_id=pid,
                action=apply_result.action,
                source="response",
                notes=notes,
            )

    if settings.PARSER_ENABLE_RUNTIME_RECONCILIATION:
        rt = runtime_ids or {}
        lid = str(rt.get("crm_listing_id") or "").strip() or None
        pid = str(rt.get("crm_product_id") or "").strip() or None
        if lid or pid:
            notes.append("used_runtime_bridge")
            return ReconciliationResult(
                resolved=True,
                crm_listing_id=lid,
                crm_product_id=pid,
                action=None,
                source="runtime",
                notes=notes,
            )

    if settings.PARSER_ENABLE_CATALOG_FIND_RECONCILIATION:
        notes.append("catalog_find_enabled_but_not_implemented_in_parser_transport")
        return ReconciliationResult(
            resolved=False,
            source="catalog_find",
            notes=notes,
        )

    if settings.PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND:
        notes.append("recommend_safe_resend_product_found_if_policy_allows")
        return ReconciliationResult(
            resolved=False,
            source="resend",
            notes=notes,
        )

    return ReconciliationResult(resolved=False, source="response", notes=notes + ["unresolved"])


def reconcile_after_ambiguous_response(
    identity: CrmIdentityContext,
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> ReconciliationResult:
    """After ambiguous CRM action, prefer runtime/catalog before resend."""
    notes: list[str] = ["ambiguous_action"]
    base = reconcile_missing_ids(identity, normalized, runtime_ids=runtime_ids, apply_result=None)
    return base.model_copy(update={"notes": list(dict.fromkeys(base.notes + notes))})
