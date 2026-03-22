from __future__ import annotations

from unittest.mock import patch

from application.lifecycle.replay_policy import (
    can_safely_resend,
    choose_replay_mode,
    should_downgrade_replay_to_product_found,
)


def _norm():
    return {
        "store": "s",
        "url": "https://x/p",
        "title": "T",
        "title_clean": "T",
        "source_id": "1",
        "external_ids": {"s": "1"},
        "price_raw": "1",
        "price_value": 10,
        "currency": "UZS",
        "in_stock": True,
        "raw_specs": {},
        "image_urls": [],
    }


def test_choose_replay_mode_product_found() -> None:
    with patch.multiple(
        "application.lifecycle.replay_policy.settings",
        PARSER_REPLAY_MODE_DEFAULT="snapshot_upsert",
        PARSER_IDEMPOTENCY_SCOPE_DEFAULT="entity_payload",
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
        PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS=False,
    ):
        rd = choose_replay_mode(_norm(), "product_found", None)
        assert rd.selected_event_type == "product_found"
        assert rd.safe_to_resend is True
        assert rd.request_idempotency_key.startswith("idemp:v1:entity_payload:")


def test_delta_not_safe_resend_without_flag() -> None:
    with patch.multiple(
        "application.lifecycle.replay_policy.settings",
        PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS=False,
        PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND=True,
    ):
        assert can_safely_resend("price_changed", {"crm_listing_id": "L1"}) is False


def test_should_downgrade_without_runtime_ids() -> None:
    assert should_downgrade_replay_to_product_found("price_changed", None) is True
    assert should_downgrade_replay_to_product_found("price_changed", {"crm_listing_id": "L1"}) is False
