from __future__ import annotations

from config.settings import settings
from domain.operational_policy import AlertSeverity, ServiceStatus, ThresholdDecision

# Metric names (stable contract for alerts / dashboards)
METRIC_PARSE_SUCCESS_RATE = "parse_success_rate"
METRIC_APPLY_SUCCESS_RATE = "apply_success_rate"
METRIC_BLOCK_PAGE_RATE = "block_page_rate"
METRIC_ZERO_RESULT_CATEGORY_RATE = "zero_result_category_rate"
METRIC_LOW_COVERAGE_RATE = "low_coverage_rate"
METRIC_REJECTED_ITEM_RATE = "rejected_item_rate"
METRIC_RETRYABLE_FAILURE_RATE = "retryable_failure_rate"
METRIC_MALFORMED_RESPONSE_RATE = "malformed_response_rate"
METRIC_UNRESOLVED_RECONCILIATION_RATE = "unresolved_reconciliation_rate"
METRIC_DUPLICATE_PAYLOAD_SKIP_RATE = "duplicate_payload_skip_rate"
METRIC_MIN_ITEMS_PER_STORE = "min_items_per_active_store"


def compute_rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _f(counters: dict[str, int | float], key: str) -> float:
    v = counters.get(key, 0)
    return float(v) if isinstance(v, (int, float)) else 0.0


def _decision(
    *,
    metric_name: str,
    observed: float,
    threshold: float,
    comparator: str,
    severity_if_breach: AlertSeverity | None,
    notes: list[str],
) -> ThresholdDecision:
    if comparator == "lt":
        breached = observed < threshold
    elif comparator == "gt":
        breached = observed > threshold
    elif comparator == "ge":
        breached = observed >= threshold
    else:
        breached = False
    return ThresholdDecision(
        metric_name=metric_name,
        observed_value=round(observed, 6),
        threshold_value=threshold,
        comparator=comparator,
        breached=breached,
        severity=severity_if_breach if breached else None,
        notes=notes,
    )


def evaluate_store_thresholds(store_name: str, counters: dict[str, int | float]) -> list[ThresholdDecision]:
    """Evaluate SLO thresholds for a store-scoped counter map (often same as run-global)."""
    _ = store_name
    return _evaluate_rates_from_counters(counters)


def evaluate_run_thresholds(run_counters: dict[str, int | float]) -> list[ThresholdDecision]:
    """Evaluate SLO thresholds for merged run-level counters."""
    return _evaluate_rates_from_counters(run_counters)


def _evaluate_rates_from_counters(c: dict[str, int | float]) -> list[ThresholdDecision]:
    out: list[ThresholdDecision] = []

    # Parse success: prefer crawl registry style keys when merged from spider snapshot
    yielded = _f(c, "product_items_yielded_total")
    parse_failed = _f(c, "product_parse_failed_total")
    parse_denom = yielded + parse_failed
    if parse_denom <= 0:
        prod_ok = _f(c, "crawl_product_pages_total")
        crawl_fail = _f(c, "crawl_failures_total")
        parse_rate = compute_rate(prod_ok, prod_ok + crawl_fail)
        parse_notes = ["from_observability_crawl_counters"]
    else:
        parse_rate = compute_rate(yielded, parse_denom)
        parse_notes = ["from_crawl_registry_yield_vs_failed"]
    out.append(
        _decision(
            metric_name=METRIC_PARSE_SUCCESS_RATE,
            observed=parse_rate,
            threshold=settings.SLO_MIN_PARSE_SUCCESS_RATE,
            comparator="lt",
            severity_if_breach="high",
            notes=parse_notes,
        )
    )

    delivery_items = _f(c, "delivery_items_total")
    applied = _f(c, "crm_applied_total")
    apply_rate = compute_rate(applied, delivery_items) if delivery_items > 0 else 1.0
    out.append(
        _decision(
            metric_name=METRIC_APPLY_SUCCESS_RATE,
            observed=apply_rate,
            threshold=settings.SLO_MIN_APPLY_SUCCESS_RATE,
            comparator="lt",
            severity_if_breach="high",
            notes=["crm_applied_over_delivery_items"],
        )
    )

    listing_pages = _f(c, "listing_pages_seen_total")
    if listing_pages <= 0:
        listing_pages = _f(c, "crawl_listing_pages_total")
    blocks = _f(c, "block_pages_total")
    block_rate = compute_rate(blocks, listing_pages) if listing_pages > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_BLOCK_PAGE_RATE,
            observed=block_rate,
            threshold=settings.SLO_MAX_BLOCK_PAGE_RATE,
            comparator="gt",
            severity_if_breach="critical",
            notes=["block_pages_over_listing_pages"],
        )
    )

    cat_started = _f(c, "categories_started_total")
    zero_cat = _f(c, "categories_zero_result_total")
    zero_rate = compute_rate(zero_cat, cat_started) if cat_started > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_ZERO_RESULT_CATEGORY_RATE,
            observed=zero_rate,
            threshold=settings.SLO_MAX_ZERO_RESULT_CATEGORY_RATE,
            comparator="gt",
            severity_if_breach="warning",
            notes=["zero_result_categories_over_categories_started"],
        )
    )

    norm_items = _f(c, "normalization_items_total")
    low_cov = _f(c, "normalization_low_coverage_total")
    low_rate = compute_rate(low_cov, norm_items) if norm_items > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_LOW_COVERAGE_RATE,
            observed=low_rate,
            threshold=settings.SLO_MAX_LOW_COVERAGE_RATE,
            comparator="gt",
            severity_if_breach="warning",
            notes=["low_coverage_over_normalized_items"],
        )
    )

    rejected = _f(c, "crm_rejected_total")
    rej_rate = compute_rate(rejected, delivery_items) if delivery_items > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_REJECTED_ITEM_RATE,
            observed=rej_rate,
            threshold=settings.SLO_MAX_REJECTED_ITEM_RATE,
            comparator="gt",
            severity_if_breach="high",
            notes=["rejected_over_delivery_items"],
        )
    )

    retryable = _f(c, "crm_retryable_total")
    retry_rate = compute_rate(retryable, delivery_items) if delivery_items > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_RETRYABLE_FAILURE_RATE,
            observed=retry_rate,
            threshold=settings.SLO_MAX_RETRYABLE_FAILURE_RATE,
            comparator="gt",
            severity_if_breach="warning",
            notes=["retryable_over_delivery_items"],
        )
    )

    batches = _f(c, "delivery_batches_total")
    malformed = _f(c, "malformed_batch_responses_total")
    mal_rate = compute_rate(malformed, batches) if batches > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_MALFORMED_RESPONSE_RATE,
            observed=mal_rate,
            threshold=settings.SLO_MAX_MALFORMED_RESPONSE_RATE,
            comparator="gt",
            severity_if_breach="critical",
            notes=["malformed_batch_over_batches"],
        )
    )

    recon_started = _f(c, "reconciliation_started_total")
    recon_failed = _f(c, "reconciliation_failed_total")
    recon_rate = compute_rate(recon_failed, recon_started) if recon_started > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_UNRESOLVED_RECONCILIATION_RATE,
            observed=recon_rate,
            threshold=settings.SLO_MAX_UNRESOLVED_RECONCILIATION_RATE,
            comparator="gt",
            severity_if_breach="critical",
            notes=["reconciliation_failed_over_started"],
        )
    )

    dup = _f(c, "duplicate_payload_skipped_total")
    dup_rate = compute_rate(dup, delivery_items) if delivery_items > 0 else 0.0
    out.append(
        _decision(
            metric_name=METRIC_DUPLICATE_PAYLOAD_SKIP_RATE,
            observed=dup_rate,
            threshold=settings.SLO_MAX_DUPLICATE_PAYLOAD_SKIP_RATE,
            comparator="gt",
            severity_if_breach="info",
            notes=["duplicate_skips_over_delivery_items"],
        )
    )

    min_items = float(settings.SLO_MIN_ITEMS_PER_ACTIVE_STORE)
    out.append(
        _decision(
            metric_name=METRIC_MIN_ITEMS_PER_STORE,
            observed=float(delivery_items),
            threshold=min_items,
            comparator="lt",
            severity_if_breach="warning" if delivery_items > 0 else "info",
            notes=["delivery_items_below_minimum_for_active_store"],
        )
    )

    return out


def decide_status_from_thresholds(decisions: list[ThresholdDecision]) -> ServiceStatus:
    """Map breached thresholds to aggregate service status."""
    breached = [d for d in decisions if d.breached]
    if not breached:
        return "healthy"
    sev_order = {"critical": 3, "high": 2, "warning": 1, "info": 0}
    worst = 0
    for d in breached:
        s = d.severity or "warning"
        worst = max(worst, sev_order.get(s, 1))
    if worst >= 3:
        return "failing"
    if worst >= 2:
        return "degraded"
    if worst >= 1:
        return "degraded"
    return "healthy"
