from __future__ import annotations

from application.governance.anti_patterns import (
    explain_anti_pattern,
    list_known_anti_patterns,
    suggest_refactor_for_anti_pattern,
)


def test_list_contains_expected() -> None:
    names = list_known_anti_patterns()
    assert "direct_cross_layer_import" in names
    assert "raw_payload_logged_directly" in names


def test_explain_returns_text() -> None:
    assert "spider" in explain_anti_pattern("spider_contains_transport_logic").lower()


def test_suggest_refactor_non_empty() -> None:
    lines = suggest_refactor_for_anti_pattern("unbounded_runtime_buffer")
    assert len(lines) >= 2
