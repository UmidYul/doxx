from __future__ import annotations

from config.settings import settings
from infrastructure.access.resource_governance import (
    apply_governance_to_request_meta,
    record_request_scheduled_governance,
    release_request_governance_counters,
)
from infrastructure.performance.resource_tracker import (
    build_runtime_state,
    reset_resource_tracker_for_tests,
)


def test_store_bypass_allows_request_without_inflight_counters(monkeypatch) -> None:
    reset_resource_tracker_for_tests()
    monkeypatch.setattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True)
    monkeypatch.setattr(settings, "ENABLE_STORE_RESOURCE_BUDGETS", True)
    monkeypatch.setattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", False)
    monkeypatch.setattr(settings, "SCRAPY_RESOURCE_GOV_BYPASS_STORES", ["alifshop"])

    meta: dict[str, object] = {"access_mode_selected": "plain"}
    admitted_meta, admitted = apply_governance_to_request_meta("alifshop", "product", meta)

    assert admitted is True
    assert admitted_meta.get("_resource_gov_bypass") is True

    record_request_scheduled_governance("alifshop", "product", admitted_meta)
    state = build_runtime_state("alifshop")
    assert state.inflight_requests == 0
    assert state.inflight_product_requests == 0

    release_request_governance_counters(admitted_meta, "alifshop")
    state_after = build_runtime_state("alifshop")
    assert state_after.inflight_requests == 0
    assert state_after.inflight_product_requests == 0


def test_non_bypassed_store_updates_inflight_counters(monkeypatch) -> None:
    reset_resource_tracker_for_tests()
    monkeypatch.setattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True)
    monkeypatch.setattr(settings, "ENABLE_STORE_RESOURCE_BUDGETS", True)
    monkeypatch.setattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", False)
    monkeypatch.setattr(settings, "SCRAPY_RESOURCE_GOV_BYPASS_STORES", [])

    meta: dict[str, object] = {"access_mode_selected": "plain"}
    admitted_meta, admitted = apply_governance_to_request_meta("mediapark", "product", meta)

    assert admitted is True
    assert admitted_meta.get("_resource_gov_bypass") is None

    record_request_scheduled_governance("mediapark", "product", admitted_meta)
    state = build_runtime_state("mediapark")
    assert state.inflight_requests == 1
    assert state.inflight_product_requests == 1

    release_request_governance_counters(admitted_meta, "mediapark")
    state_after = build_runtime_state("mediapark")
    assert state_after.inflight_requests == 0
    assert state_after.inflight_product_requests == 0
