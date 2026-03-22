from __future__ import annotations

from typing import Any, Literal

from domain.cost_efficiency import CostRegressionResult

Direction = Literal["higher_worse", "lower_worse"]


def compare_metric_against_baseline(
    metric_name: str,
    baseline: float,
    current: float,
    allowed_delta_pct: float,
    *,
    direction: Direction = "higher_worse",
) -> CostRegressionResult:
    if baseline == 0.0 and current == 0.0:
        return CostRegressionResult(
            passed=True,
            metric_name=metric_name,
            baseline_value=baseline,
            current_value=current,
            allowed_delta_pct=allowed_delta_pct,
            regression_pct=0.0,
            reason="both_zero",
        )
    if baseline == 0.0:
        return CostRegressionResult(
            passed=False,
            metric_name=metric_name,
            baseline_value=baseline,
            current_value=current,
            allowed_delta_pct=allowed_delta_pct,
            regression_pct=100.0,
            reason="baseline_zero_nonzero_current",
        )

    if direction == "higher_worse":
        worsened = current > baseline * (1.0 + allowed_delta_pct / 100.0)
        regression_pct = ((current - baseline) / abs(baseline)) * 100.0 if baseline != 0 else 0.0
    else:
        worsened = current < baseline * (1.0 - allowed_delta_pct / 100.0)
        regression_pct = ((baseline - current) / abs(baseline)) * 100.0 if baseline != 0 else 0.0

    passed = not worsened
    reason = "within_tolerance" if passed else "regression_beyond_allowed_delta"
    return CostRegressionResult(
        passed=passed,
        metric_name=metric_name,
        baseline_value=baseline,
        current_value=current,
        allowed_delta_pct=allowed_delta_pct,
        regression_pct=float(regression_pct),
        reason=reason,
    )


def evaluate_perf_regressions(
    baseline: dict[str, float],
    current: dict[str, float],
    settings: Any,
) -> list[CostRegressionResult]:
    if not getattr(settings, "ENABLE_COST_REGRESSION_GATES", True):
        return []

    checks: list[tuple[str, str, Direction]] = [
        ("avg_request_ms", "PERF_REGRESSION_MAX_REQUEST_MS_DELTA_PCT", "higher_worse"),
        ("avg_normalize_ms", "PERF_REGRESSION_MAX_NORMALIZE_MS_DELTA_PCT", "higher_worse"),
        ("avg_crm_send_ms", "PERF_REGRESSION_MAX_CRM_SEND_MS_DELTA_PCT", "higher_worse"),
        ("cost_per_product", "PERF_REGRESSION_MAX_COST_PER_PRODUCT_DELTA_PCT", "higher_worse"),
        ("cost_per_applied_item", "PERF_REGRESSION_MAX_COST_PER_PRODUCT_DELTA_PCT", "higher_worse"),
        ("products_per_minute", "PERF_REGRESSION_MAX_REQUEST_MS_DELTA_PCT", "lower_worse"),
    ]

    out: list[CostRegressionResult] = []
    for key, setting_name, direction in checks:
        if key not in baseline or key not in current:
            continue
        b = float(baseline[key])
        c = float(current[key])
        pct = float(getattr(settings, setting_name, 25.0))
        out.append(
            compare_metric_against_baseline(
                key,
                b,
                c,
                pct,
                direction=direction,
            )
        )
    return out


def should_fail_perf_gate(results: list[CostRegressionResult]) -> bool:
    return any(not r.passed for r in results)


def log_perf_regression_evaluation(
    results: list[CostRegressionResult],
    settings: Any,
) -> None:
    """Emit structured logs for release/CI when comparing baselines (8C)."""
    if not getattr(settings, "ENABLE_COST_REGRESSION_GATES", True):
        return
    from infrastructure.observability import message_codes as cm
    from infrastructure.observability.event_logger import log_cost_efficiency_event

    for r in results:
        if r.passed:
            continue
        log_cost_efficiency_event(
            cm.COST_REGRESSION_DETECTED,
            metric_name=r.metric_name,
            baseline_value=r.baseline_value,
            current_value=r.current_value,
            regression_pct=r.regression_pct,
            details={"reason": r.reason, "allowed_delta_pct": r.allowed_delta_pct},
        )
    if should_fail_perf_gate(results):
        log_cost_efficiency_event(
            cm.COST_REGRESSION_GATE_FAILED,
            details={"failed_metrics": [r.metric_name for r in results if not r.passed]},
        )
