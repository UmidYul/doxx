from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.lifecycle.idempotency import (
    build_request_idempotency_key,
    build_snapshot_fingerprint,
    is_replay_safe_event_type,
)


def test_product_found_same_key_same_snapshot() -> None:
    k1 = build_request_idempotency_key("s:1", "sha256:aaa", "product_found", "entity_payload")
    k2 = build_request_idempotency_key("s:1", "sha256:aaa", "product_found", "entity_payload")
    assert k1 == k2


def test_event_id_not_in_key() -> None:
    k = build_request_idempotency_key("s:1", "sha256:bbb", "product_found", "entity_payload")
    assert str(uuid.uuid4()) not in k


def test_different_event_type_changes_key() -> None:
    a = build_request_idempotency_key("s:1", "sha256:aaa", "product_found", "entity_payload")
    b = build_request_idempotency_key("s:1", "sha256:aaa", "price_changed", "entity_payload")
    assert a != b


def test_entity_only_scope_ignores_payload_hash() -> None:
    a = build_request_idempotency_key("s:1", "sha256:aaa", "product_found", "entity_only")
    b = build_request_idempotency_key("s:1", "sha256:bbb", "product_found", "entity_only")
    assert a == b


def test_event_only_scope_raises() -> None:
    with pytest.raises(ValueError):
        build_request_idempotency_key("s:1", "sha256:a", "product_found", "event_only")


def test_snapshot_fingerprint_stable() -> None:
    n = {"store": "x", "url": "https://u", "source_id": "1", "title_clean": "T", "price_value": 1, "in_stock": True}
    assert build_snapshot_fingerprint(n) == build_snapshot_fingerprint(dict(n))


def test_replay_safe_flags() -> None:
    assert is_replay_safe_event_type("product_found") is True
    with patch("application.lifecycle.idempotency.settings") as s:
        s.PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS = False
        assert is_replay_safe_event_type("price_changed") is False
