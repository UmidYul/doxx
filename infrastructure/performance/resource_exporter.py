from __future__ import annotations

from typing import Any

from domain.resource_governance import (
    BackpressureDecision,
    RuntimeResourceState,
    StoreResourceBudget,
)


def build_resource_state_payload(state: RuntimeResourceState) -> dict[str, Any]:
    return {
        "kind": "runtime_resource_state_v1",
        "store_name": state.store_name,
        "inflight_requests": state.inflight_requests,
        "inflight_listing_requests": state.inflight_listing_requests,
        "inflight_product_requests": state.inflight_product_requests,
        "inflight_batches": state.inflight_batches,
        "queued_retryable_items": state.queued_retryable_items,
        "active_browser_pages": state.active_browser_pages,
        "active_proxy_requests": state.active_proxy_requests,
        "memory_mb": state.memory_mb,
    }


def build_store_budget_payload(budget: StoreResourceBudget) -> dict[str, Any]:
    return {
        "kind": "store_resource_budget_v1",
        "store_name": budget.store_name,
        "max_concurrent_requests": budget.max_concurrent_requests,
        "max_listing_requests": budget.max_listing_requests,
        "max_product_requests": budget.max_product_requests,
        "max_batch_inflight": budget.max_batch_inflight,
        "max_retryable_queue": budget.max_retryable_queue,
        "max_browser_pages": budget.max_browser_pages,
        "max_proxy_requests": budget.max_proxy_requests,
        "max_memory_mb": budget.max_memory_mb,
        "notes": list(budget.notes),
    }


def build_backpressure_payload(decision: BackpressureDecision) -> dict[str, Any]:
    return {
        "kind": "backpressure_decision_v1",
        "store_name": decision.store_name,
        "apply_backpressure": decision.apply_backpressure,
        "reason": decision.reason,
        "severity": decision.severity,
        "suggested_action": decision.suggested_action,
    }
