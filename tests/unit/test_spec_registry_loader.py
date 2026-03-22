from __future__ import annotations

import pytest

from application.extractors.spec_registry_loader import (
    clear_spec_registry_cache,
    get_alias_rules,
    get_category_policy,
    get_field_definitions,
    get_store_overrides,
    load_spec_registry,
)
from config.settings import settings


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    clear_spec_registry_cache()
    yield
    clear_spec_registry_cache()


def test_load_spec_registry_deterministic():
    a = load_spec_registry()
    b = load_spec_registry()
    assert len(a["alias_rules"]) == len(b["alias_rules"])


def test_category_specific_overrides_common_weight_alias():
    rules = [r for r in get_alias_rules("laptop", None) if r.raw_label == "вес"]
    assert rules, "expected normalized 'вес' rules"
    assert rules[0].typed_field == "weight_kg"


def test_phone_policy_has_ram():
    p = get_category_policy("phone")
    assert "ram_gb" in p.enabled_fields


def test_get_field_definitions_respects_enabled():
    fds = get_field_definitions("unknown")
    assert "hdmi_count" not in fds
    assert "ram_gb" in fds


def test_get_store_overrides_mediapark():
    ov = get_store_overrides("mediapark", "phone")
    assert ov is not None
    assert any("оператив" in r.raw_label for r in ov.alias_overrides)


def test_disable_store_overrides_via_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENABLE_STORE_SPEC_OVERRIDES", False)
    clear_spec_registry_cache()
    assert get_store_overrides("mediapark", None) is None
    reg = load_spec_registry()
    assert reg["store_overrides"] == ()
