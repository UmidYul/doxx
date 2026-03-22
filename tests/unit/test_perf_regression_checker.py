from __future__ import annotations

from types import SimpleNamespace

from application.performance.perf_regression_checker import (
    compare_metric_against_baseline,
    evaluate_perf_regressions,
    should_fail_perf_gate,
)


def test_detects_latency_regression_beyond_delta() -> None:
    r = compare_metric_against_baseline("avg_request_ms", 100.0, 150.0, 25.0, direction="higher_worse")
    assert not r.passed
    assert r.regression_pct > 0


def test_small_additive_drift_passes() -> None:
    r = compare_metric_against_baseline("avg_request_ms", 100.0, 110.0, 25.0, direction="higher_worse")
    assert r.passed


def test_lower_worse_throughput_drop() -> None:
    r = compare_metric_against_baseline("products_per_minute", 100.0, 50.0, 25.0, direction="lower_worse")
    assert not r.passed


def test_evaluate_perf_regressions_respects_gate_flag() -> None:
    s = SimpleNamespace(
        ENABLE_COST_REGRESSION_GATES=False,
        PERF_REGRESSION_MAX_REQUEST_MS_DELTA_PCT=25.0,
        PERF_REGRESSION_MAX_NORMALIZE_MS_DELTA_PCT=25.0,
        PERF_REGRESSION_MAX_CRM_SEND_MS_DELTA_PCT=25.0,
        PERF_REGRESSION_MAX_COST_PER_PRODUCT_DELTA_PCT=30.0,
    )
    assert evaluate_perf_regressions({"avg_request_ms": 1.0}, {"avg_request_ms": 9.0}, s) == []


def test_should_fail_perf_gate() -> None:
    from domain.cost_efficiency import CostRegressionResult

    bad = CostRegressionResult(
        passed=False,
        metric_name="m",
        baseline_value=1.0,
        current_value=2.0,
        allowed_delta_pct=1.0,
        regression_pct=100.0,
        reason="x",
    )
    good = bad.model_copy(update={"passed": True})
    assert should_fail_perf_gate([good]) is False
    assert should_fail_perf_gate([bad]) is True
