from __future__ import annotations

import pytest

from application.release.contract_evolution import (
    classify_contract_change,
    detect_behavioral_change,
    is_additive_field_change,
    is_breaking_field_change,
)
from application.release.deprecation_registry import (
    clear_deprecation_registry_for_tests,
    register_deprecation_notice,
)
from domain.compatibility import DeprecationNotice


@pytest.fixture(autouse=True)
def _clear_deprecation_registry() -> None:
    clear_deprecation_registry_for_tests()
    yield
    clear_deprecation_registry_for_tests()


def test_adding_optional_field_additive() -> None:
    base = {"a": 1, "entity_key": "x", "payload_hash": "h", "source_name": "s", "source_url": "u"}
    cur = dict(base)
    cur["new_opt"] = "x"
    changes = classify_contract_change("crm_payload", base, cur)
    additive = [c for c in changes if c.change_type == "additive"]
    assert additive
    assert not any(c.compatibility_level == "breaking" for c in changes)


def test_removing_required_field_breaking() -> None:
    base = {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "http://x", "schema_version": 1}
    cur = {k: v for k, v in base.items() if k != "entity_key"}
    changes = classify_contract_change("crm_payload", base, cur)
    assert any(c.compatibility_level == "breaking" for c in changes)


def test_rename_without_shadow_breaking() -> None:
    base = {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1, "old_title": "t"}
    cur = {
        "entity_key": "k",
        "payload_hash": "h",
        "source_name": "s",
        "source_url": "u",
        "schema_version": 1,
        "new_title": "t",
    }
    changes = classify_contract_change("crm_payload", base, cur)
    assert any(c.compatibility_level == "breaking" for c in changes)


def test_rename_with_shadow_conditionally_compatible() -> None:
    register_deprecation_notice(
        DeprecationNotice(
            surface="crm_payload",
            field_name="old_title",
            status="shadow",
            replacement_field="new_title",
            deprecation_reason="rename",
        )
    )
    base = {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1, "old_title": "t"}
    cur = {
        "entity_key": "k",
        "payload_hash": "h",
        "source_name": "s",
        "source_url": "u",
        "schema_version": 1,
        "new_title": "t",
    }
    changes = classify_contract_change("crm_payload", base, cur)
    assert any(c.change_name.startswith("shadow_rename:") for c in changes)
    assert not any(c.change_name.startswith("removed_field:old_title") for c in changes)
    assert any(c.compatibility_level == "conditionally_compatible" for c in changes)


def test_type_drift_required_field_breaking() -> None:
    base = {"entity_key": "k", "payload_hash": "h", "source_name": "s", "source_url": "u", "schema_version": 1}
    cur = dict(base)
    cur["entity_key"] = 123  # type: ignore[assignment]
    changes = classify_contract_change("crm_payload", base, cur)
    assert any("type_or_shape_drift" in c.change_name for c in changes)


def test_is_additive_field_change() -> None:
    assert is_additive_field_change({"a": 1}, {"a": 1, "b": 2})
    assert not is_additive_field_change({"a": 1}, {"b": 2})


def test_is_breaking_field_change_types() -> None:
    assert is_breaking_field_change("a", 1)
    assert not is_breaking_field_change(1, 2)


def test_lifecycle_default_event_semantic_drift() -> None:
    b = {"lifecycle_default_event": "product_found"}
    a = {"lifecycle_default_event": "price_changed"}
    ch = detect_behavioral_change("lifecycle_event", b, a)
    assert ch
    assert any(c.change_type == "breaking" for c in ch)


def test_etl_status_critical_field_removal_breaking() -> None:
    base: dict[str, object] = {
        "schema": "parser_etl_status_v3",
        "run_id": "r1",
        "current_status": "ok",
        "counters_summary": {},
    }
    cur = {k: v for k, v in base.items() if k != "counters_summary"}
    changes = classify_contract_change("etl_status", base, cur)
    assert any(c.compatibility_level == "breaking" for c in changes)
