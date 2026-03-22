from __future__ import annotations

from infrastructure.observability.replay_support import (
    can_replay_batch,
    can_replay_item,
    decide_safe_replay_action,
    explain_replay_risk,
)


def test_product_found_single_item_allowed(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.ENABLE_SAFE_REPLAY_SUPPORT", True)
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.SAFE_REPLAY_ALLOW_PRODUCT_FOUND", True)
    d = decide_safe_replay_action("product_found", item_count=1, batch_count=1)
    assert d.allowed is True
    assert d.safe_scope == "single_item"
    assert d.action == "replay_product_found"


def test_delta_replay_denied_by_default(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.ENABLE_SAFE_REPLAY_SUPPORT", True)
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.SAFE_REPLAY_ALLOW_DELTA_EVENTS", False)
    monkeypatch.setattr(
        "infrastructure.observability.replay_support.settings.SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY", True
    )
    assert can_replay_item("price_changed") is False
    d = decide_safe_replay_action("price_changed", item_count=1, batch_count=1)
    assert d.allowed is False
    assert "PRODUCT_FOUND" in (d.reason or "") or "delta" in explain_replay_risk("price_changed").lower()


def test_homogeneous_batch_within_limits(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.ENABLE_SAFE_REPLAY_SUPPORT", True)
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.SAFE_REPLAY_MAX_ITEMS_PER_ACTION", 20)
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.SAFE_REPLAY_MAX_BATCHES_PER_ACTION", 3)
    d = decide_safe_replay_action("product_found", item_count=10, batch_count=1)
    assert d.allowed is True
    assert d.safe_scope == "single_batch"


def test_can_replay_batch_requires_single_event_type(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.replay_support.settings.SAFE_REPLAY_ALLOW_PRODUCT_FOUND", True)
    assert can_replay_batch(["product_found", "product_found"]) is True
    assert can_replay_batch(["product_found", "price_changed"]) is False
