from __future__ import annotations

import pytest

from config import settings as settings_mod
from domain.operational_policy import ThresholdDecision

from infrastructure.observability.threshold_evaluator import (
    METRIC_BLOCK_PAGE_RATE,
    METRIC_LOW_COVERAGE_RATE,
    METRIC_PARSE_SUCCESS_RATE,
    compute_rate,
    decide_status_from_thresholds,
    evaluate_run_thresholds,
    evaluate_store_thresholds,
)


def test_compute_rate_zero_denominator():
    assert compute_rate(5.0, 0.0) == 0.0


def test_parse_success_below_slo_is_degraded_or_failing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_mod.settings, "SLO_MIN_PARSE_SUCCESS_RATE", 0.99)
    c = {
        "product_items_yielded_total": 10.0,
        "product_parse_failed_total": 50.0,
        "delivery_items_total": 100.0,
        "crm_applied_total": 100.0,
        "listing_pages_seen_total": 100.0,
        "categories_started_total": 10.0,
        "normalization_items_total": 100.0,
        "delivery_batches_total": 10.0,
        "reconciliation_started_total": 10.0,
    }
    decs = evaluate_run_thresholds(c)
    parse_d = next(d for d in decs if d.metric_name == METRIC_PARSE_SUCCESS_RATE)
    assert parse_d.breached is True
    assert decide_status_from_thresholds(decs) in ("degraded", "failing")


def test_block_page_spike_breaches(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_mod.settings, "SLO_MAX_BLOCK_PAGE_RATE", 0.05)
    c = {
        "block_pages_total": 10.0,
        "listing_pages_seen_total": 20.0,
        "product_items_yielded_total": 100.0,
        "product_parse_failed_total": 0.0,
        "delivery_items_total": 100.0,
        "crm_applied_total": 100.0,
        "categories_started_total": 10.0,
        "normalization_items_total": 100.0,
        "delivery_batches_total": 10.0,
        "reconciliation_started_total": 10.0,
    }
    decs = evaluate_run_thresholds(c)
    b = next(d for d in decs if d.metric_name == METRIC_BLOCK_PAGE_RATE)
    assert b.breached is True
    assert b.severity == "critical"


def test_low_coverage_warning_not_immediately_failing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_mod.settings, "SLO_MAX_LOW_COVERAGE_RATE", 0.10)
    c = {
        "normalization_low_coverage_total": 15.0,
        "normalization_items_total": 100.0,
        "product_items_yielded_total": 100.0,
        "product_parse_failed_total": 0.0,
        "delivery_items_total": 100.0,
        "crm_applied_total": 100.0,
        "listing_pages_seen_total": 100.0,
        "categories_started_total": 10.0,
        "delivery_batches_total": 10.0,
        "reconciliation_started_total": 10.0,
    }
    decs = evaluate_run_thresholds(c)
    lc = next(d for d in decs if d.metric_name == METRIC_LOW_COVERAGE_RATE)
    assert lc.breached is True
    st = decide_status_from_thresholds(decs)
    assert st in ("healthy", "degraded")


def test_evaluate_store_matches_run_shape():
    c = {
        "product_items_yielded_total": 80.0,
        "product_parse_failed_total": 20.0,
        "delivery_items_total": 50.0,
        "crm_applied_total": 48.0,
        "listing_pages_seen_total": 40.0,
        "categories_started_total": 5.0,
        "normalization_items_total": 50.0,
        "delivery_batches_total": 5.0,
        "reconciliation_started_total": 5.0,
        "reconciliation_failed_total": 0.0,
    }
    a = evaluate_store_thresholds("s1", c)
    b = evaluate_run_thresholds(c)
    assert len(a) == len(b)
    assert all(isinstance(x, ThresholdDecision) for x in a)
