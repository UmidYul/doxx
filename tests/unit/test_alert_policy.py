from __future__ import annotations

from domain.operational_policy import ThresholdDecision

from infrastructure.observability.alert_policy import (
    build_alerts_from_thresholds,
    classify_alert_domain,
    decide_alert_severity,
)
from infrastructure.observability.threshold_evaluator import METRIC_BLOCK_PAGE_RATE, METRIC_LOW_COVERAGE_RATE


def test_classify_domain():
    assert classify_alert_domain(METRIC_BLOCK_PAGE_RATE) == "store_access"
    assert classify_alert_domain(METRIC_LOW_COVERAGE_RATE) == "normalization_quality"


def test_decide_severity_block_vs_low_coverage():
    s_block = decide_alert_severity(METRIC_BLOCK_PAGE_RATE, 0.5, 0.1)
    assert s_block in ("high", "critical")
    s_low = decide_alert_severity(METRIC_LOW_COVERAGE_RATE, 0.4, 0.35)
    assert s_low in ("info", "warning")


def test_build_alerts_from_thresholds_only_breached():
    decs = [
        ThresholdDecision(
            metric_name=METRIC_LOW_COVERAGE_RATE,
            observed_value=0.5,
            threshold_value=0.35,
            comparator="gt",
            breached=True,
            severity="warning",
        ),
        ThresholdDecision(
            metric_name=METRIC_LOW_COVERAGE_RATE,
            observed_value=0.1,
            threshold_value=0.35,
            comparator="gt",
            breached=False,
            severity=None,
        ),
    ]
    alerts = build_alerts_from_thresholds("run1", "store_a", decs)
    assert len(alerts) == 1
    assert alerts[0].run_id == "run1"
    assert alerts[0].store_name == "store_a"
