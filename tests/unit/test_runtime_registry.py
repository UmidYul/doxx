from __future__ import annotations

from unittest.mock import patch

import pytest

from infrastructure.sync.runtime_registry import RuntimeSyncRegistry


@pytest.fixture
def registry() -> RuntimeSyncRegistry:
    return RuntimeSyncRegistry()


def test_should_skip_after_successful_remember(registry: RuntimeSyncRegistry) -> None:
    assert registry.should_skip("store:1", "h1") is False
    registry.remember_payload("store:1", "h1")
    assert registry.should_skip("store:1", "h1") is True


def test_same_entity_new_hash_not_skipped(registry: RuntimeSyncRegistry) -> None:
    registry.remember_payload("store:1", "h1")
    assert registry.should_skip("store:1", "h2") is False


def test_remember_crm_ids_and_get(registry: RuntimeSyncRegistry) -> None:
    registry.remember_crm_ids("store:1", "L1", "P1", "updated")
    assert registry.get_crm_ids("store:1") == ("L1", "P1")


def test_dedupe_disabled_via_settings(registry: RuntimeSyncRegistry) -> None:
    with patch.multiple(
        "infrastructure.sync.runtime_registry.settings",
        SYNC_DEDUPE_IN_MEMORY=False,
        SYNC_MAX_IN_MEMORY_CACHE=10000,
    ):
        registry.remember_payload("store:1", "h1")
        assert registry.should_skip("store:1", "h1") is False


def test_trim_if_needed_evicts_oldest_pairs() -> None:
    reg = RuntimeSyncRegistry()
    with patch("infrastructure.sync.runtime_registry.settings") as s:
        s.SYNC_MAX_IN_MEMORY_CACHE = 2
        reg.remember_payload("a", "h1")
        reg.remember_payload("b", "h2")
        reg.remember_payload("c", "h3")
        # Oldest pair (a,h1) dropped from dedupe set
        assert reg.should_skip("a", "h1") is False
        assert reg.should_skip("b", "h2") is True
        assert reg.should_skip("c", "h3") is True
