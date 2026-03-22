from __future__ import annotations

from types import SimpleNamespace

from infrastructure.performance.cost_model import (
    build_run_cost_snapshot,
    build_store_cost_snapshot,
    compute_products_per_cost_unit,
    estimate_store_cost_units,
)


def _settings(**kwargs: float | bool) -> SimpleNamespace:
    base = dict(
        ENABLE_COST_EFFICIENCY_TRACKING=True,
        COST_WEIGHT_HTTP_REQUEST=1.0,
        COST_WEIGHT_PROXY_REQUEST=2.0,
        COST_WEIGHT_BROWSER_PAGE=5.0,
        COST_WEIGHT_RETRY_ATTEMPT=1.5,
        COST_WEIGHT_BATCH_FLUSH=0.5,
        COST_WEIGHT_CRM_ROUNDTRIP=1.0,
        COST_WEIGHT_NORMALIZATION_UNIT=0.5,
        COST_WEIGHT_DIAGNOSTIC_UNIT=0.2,
        EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT=0.5,
        EFFICIENCY_MIN_APPLIED_PER_COST_UNIT=0.4,
        EFFICIENCY_MAX_BROWSER_SHARE=0.30,
        EFFICIENCY_MAX_RETRY_SHARE=0.20,
        EFFICIENCY_MAX_PROXY_SHARE=0.40,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_browser_proxy_raise_cost_vs_http() -> None:
    s = _settings()
    http_only = estimate_store_cost_units({"http_requests": 10}, s)
    proxy = estimate_store_cost_units({"proxy_requests": 10}, s)
    browser = estimate_store_cost_units({"browser_pages": 10}, s)
    assert proxy > http_only
    assert browser > proxy


def test_products_per_cost_unit() -> None:
    assert compute_products_per_cost_unit(10, 5.0) == 2.0
    assert compute_products_per_cost_unit(0, 5.0) is None
    assert compute_products_per_cost_unit(5, 0.0) is None


def test_build_store_snapshot_json_friendly() -> None:
    snap = build_store_cost_snapshot(
        "s",
        {
            "http_requests": 10,
            "products_parsed": 20,
            "products_applied": 15,
            "batch_flushes": 2,
            "crm_roundtrips": 2,
            "normalization_units": 4.0,
            "diagnostic_units": 1.0,
        },
        _settings(),
    )
    assert snap.store_name == "s"
    assert snap.estimated_cost_units > 0
    assert snap.products_per_cost_unit is not None


def test_build_run_snapshot() -> None:
    ctr = {
        "a": {"http_requests": 5, "products_parsed": 10, "products_applied": 8, "batch_flushes": 1, "crm_roundtrips": 1},
        "b": {"http_requests": 3, "products_parsed": 2, "products_applied": 2, "batch_flushes": 1, "crm_roundtrips": 1},
    }
    run = build_run_cost_snapshot("run-1", ctr, _settings())
    assert run.run_id == "run-1"
    assert run.total_estimated_cost_units > 0
    assert len(run.highest_cost_stores) >= 1
