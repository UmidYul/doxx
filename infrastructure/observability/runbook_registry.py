from __future__ import annotations

from domain.operator_support import RunbookAction, RunbookPlan, RunbookStep, TriageDomain


def build_runbook_steps(domain: TriageDomain, severity: str) -> list[RunbookStep]:
    sev = (severity or "warning").lower()
    _ = sev  # future: expand steps for critical

    if domain == "store_access":
        return [
            RunbookStep(
                step_order=1,
                title="Check ban / block signals",
                instruction="Review structured logs for CRAWL_FAILURE with failure_domain=anti_bot and block_pages_total vs listing pages.",
                expected_outcome="Confirm whether responses are empty shells, captchas, or HTTP anomalies.",
            ),
            RunbookStep(
                step_order=2,
                title="Validate store access profile",
                instruction="Verify store profile (headers, proxy, Playwright opt-in) matches site behavior; avoid deep spider changes in hot incident.",
                expected_outcome="Access mode aligned with site requirements.",
            ),
            RunbookStep(
                step_order=3,
                title="Advisory degrade / disable",
                instruction="If block rate SLO breached, follow ENABLE_STORE_DISABLE_ADVICE: pause store crawl in scheduler or reduce concurrency externally.",
                expected_outcome="Store isolated without parser-side auto-mutation.",
                safe_action=True,
            ),
        ]

    if domain == "crawl_quality":
        return [
            RunbookStep(
                step_order=1,
                title="Inspect parse success SLO",
                instruction="Compare product_items_yielded vs parse_failed from crawl snapshot counters in health export.",
            ),
            RunbookStep(
                step_order=2,
                title="Spot partial products",
                instruction="Filter traces for CRAWL_PRODUCT_PARTIAL and missing recommended fields patterns.",
            ),
            RunbookStep(
                step_order=3,
                title="Safe restart scope",
                instruction="Parser is stateless: rerunning spider after fixing extractor (separate change) is safe; do not bulk-replay CRM without triage.",
                safe_action=True,
            ),
        ]

    if domain == "normalization_quality":
        return [
            RunbookStep(
                step_order=1,
                title="Review low mapping coverage",
                instruction="Check NORMALIZATION_LOW_COVERAGE and spec_coverage counters; confirm category_hint sanity.",
            ),
            RunbookStep(
                step_order=2,
                title="CRM payload shape",
                instruction="CRM owns full normalization; parser only sends hybrid payload—escalate schema gaps to CRM if rejects spike.",
            ),
        ]

    if domain == "delivery_transport":
        return [
            RunbookStep(
                step_order=1,
                title="Retries and malformed batch",
                instruction="Inspect DELIVERY_RETRY traces and malformed_batch_responses_total vs delivery_batches_total.",
            ),
            RunbookStep(
                step_order=2,
                title="Batch fallback",
                instruction="Confirm CRM batch endpoint availability; transport may fall back per-item—watch partial batch success settings.",
            ),
            RunbookStep(
                step_order=3,
                title="Bounded retry",
                instruction="If policy allows, retry a single batch once after backoff; avoid blind multi-batch replay.",
                expected_outcome="One controlled re-flush",
                safe_action=True,
            ),
        ]

    if domain == "crm_apply":
        return [
            RunbookStep(
                step_order=1,
                title="Rejected vs retryable",
                instruction="Separate CRM_APPLY_REJECTED (business) from CRM_APPLY_RETRYABLE (transient) via traces.",
            ),
            RunbookStep(
                step_order=2,
                title="Schema / required fields",
                instruction="Cross-check CRM validation errors; missing external ids or entity_key mismatches often cluster.",
            ),
            RunbookStep(
                step_order=3,
                title="Downgrade consideration",
                instruction="If delta events rejected without runtime ids, lifecycle may downgrade to product_found—confirm PARSER_FORCE_PRODUCT_FOUND_FALLBACK policy.",
            ),
        ]

    if domain == "reconciliation":
        return [
            RunbookStep(
                step_order=1,
                title="Missing ids vs ambiguous",
                instruction="Filter RECONCILIATION_UNRESOLVED and parser_reconciliation_signal in apply summaries.",
            ),
            RunbookStep(
                step_order=2,
                title="Bounded product_found replay",
                instruction="Use replay_support.decide_safe_replay_action for single-item product_found only when ENABLE_SAFE_REPLAY_SUPPORT.",
                expected_outcome="One safe resend path",
                safe_action=True,
            ),
        ]

    return [
        RunbookStep(
            step_order=1,
            title="Collect diagnostic snapshot",
            instruction="Export parser_etl_status payload (v2+) and correlate run_id / batch_id with CRM audit.",
        ),
        RunbookStep(
            step_order=2,
            title="Manual investigation",
            instruction="No auto-runbook beyond gathering signals; escalate with entity_key samples only.",
        ),
    ]


def _final_action(domain: TriageDomain, severity: str) -> RunbookAction:
    sev = (severity or "").lower()
    if domain == "delivery_transport" and sev in ("high", "critical"):
        return "retry_batch_once"
    if domain == "reconciliation":
        return "replay_product_found"
    if domain == "crm_apply":
        return "investigate_manually"
    if domain == "store_access" and sev == "critical":
        return "disable_store_temporarily"
    if domain == "internal":
        return "investigate_manually"
    return "continue"


def get_runbook_for_domain(domain: TriageDomain, severity: str) -> RunbookPlan:
    steps = build_runbook_steps(domain, severity)
    return RunbookPlan(
        domain=domain,
        severity=severity,
        steps=steps,
        final_recommendation=_final_action(domain, severity),
    )
