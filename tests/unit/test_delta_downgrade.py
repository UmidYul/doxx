from __future__ import annotations

from application.lifecycle.delta_downgrade import should_downgrade_delta_event_to_product_found
from domain.crm_replay import ReplayDecision


def _rd() -> ReplayDecision:
    return ReplayDecision(
        replay_mode="snapshot_upsert",
        idempotency_scope="entity_payload",
        request_idempotency_key="k",
        selected_event_type="price_changed",
        safe_to_resend=False,
    )


def test_no_downgrade_with_listing() -> None:
    assert should_downgrade_delta_event_to_product_found("price_changed", {"crm_listing_id": "L1"}, _rd()) is False


def test_downgrade_without_listing() -> None:
    assert should_downgrade_delta_event_to_product_found("price_changed", None, _rd()) is True


def test_no_downgrade_product_found() -> None:
    assert should_downgrade_delta_event_to_product_found("product_found", None, _rd()) is False
