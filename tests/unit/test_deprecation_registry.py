from __future__ import annotations

import pytest

from application.release.deprecation_registry import (
    build_deprecation_warnings,
    clear_deprecation_registry_for_tests,
    get_deprecations,
    get_shadow_fields,
    is_field_deprecated,
    register_deprecation_notice,
)
from domain.compatibility import DeprecationNotice


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_deprecation_registry_for_tests()
    yield
    clear_deprecation_registry_for_tests()


def test_register_and_query() -> None:
    register_deprecation_notice(
        DeprecationNotice(
            surface="crm_payload",
            field_name="legacy_sku",
            status="deprecated",
            replacement_field="source_id",
            deprecation_reason="unify ids",
        )
    )
    assert is_field_deprecated("crm_payload", "legacy_sku")
    warns = build_deprecation_warnings("crm_payload", {"legacy_sku": "x"})
    assert warns


def test_shadow_mapping() -> None:
    register_deprecation_notice(
        DeprecationNotice(
            surface="etl_status",
            field_name="old_metric",
            status="shadow",
            replacement_field="counters_summary",
            deprecation_reason="rename",
        )
    )
    m = get_shadow_fields("etl_status")
    assert m.get("old_metric") == "counters_summary"


def test_get_deprecations_empty_surface() -> None:
    assert get_deprecations("unknown_surface_xyz") == []
