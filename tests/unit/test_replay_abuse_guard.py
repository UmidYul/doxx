from __future__ import annotations

from config.settings import Settings
from infrastructure.security.replay_abuse_guard import (
    is_safe_replay_event_set,
    is_safe_replay_scope,
    validate_replay_request,
)


def test_large_replay_blocked() -> None:
    s = Settings(
        _env_file=None,
        ENABLE_REPLAY_ABUSE_GUARDS=True,
        SAFE_REPLAY_MAX_ITEMS_PER_ACTION=5,
        SAFE_REPLAY_MAX_BATCHES_PER_ACTION=1,
    )  # type: ignore[arg-type]
    d = validate_replay_request(["product_found"], item_count=100, batch_count=1, settings=s)
    assert not d.allowed


def test_non_product_found_blocked_when_required() -> None:
    s = Settings(
        _env_file=None,
        ENABLE_REPLAY_ABUSE_GUARDS=True,
        SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY=True,
        SAFE_REPLAY_ALLOW_DELTA_EVENTS=True,
    )  # type: ignore[arg-type]
    d = validate_replay_request(["price_changed"], item_count=1, batch_count=1, settings=s)
    assert not d.allowed


def test_product_found_small_allowed() -> None:
    s = Settings(
        _env_file=None,
        ENABLE_REPLAY_ABUSE_GUARDS=True,
        SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY=True,
        SAFE_REPLAY_ALLOW_PRODUCT_FOUND=True,
    )  # type: ignore[arg-type]
    d = validate_replay_request(["product_found"], item_count=1, batch_count=1, settings=s)
    assert d.allowed


def test_is_safe_helpers() -> None:
    s = Settings(_env_file=None, ENABLE_REPLAY_ABUSE_GUARDS=True)  # type: ignore[arg-type]
    assert is_safe_replay_scope(1, 1, s)
    assert is_safe_replay_event_set(["product_found"], s)
