from __future__ import annotations

import json
from pathlib import Path

from config import settings as settings_mod
from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult
from tests.helpers.builders import build_parser_sync_event_fixture

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regression" / "lifecycle" / "decision_baseline.json"
BATCH_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regression" / "batch" / "apply_result_baseline.json"


def test_product_found_default_safe_event():
    assert settings_mod.settings.PARSER_EVENT_DEFAULT_TYPE == "product_found"
    assert settings_mod.settings.PARSER_LIFECYCLE_DEFAULT_EVENT == "product_found"


def test_lifecycle_decision_fixture_stable():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["selected_event_type"] == "product_found"
    assert data["allowed"] is True


def test_idempotency_key_present_on_sync_event():
    ev = build_parser_sync_event_fixture()
    assert ev.request_idempotency_key


def test_batch_apply_baseline_matches_domain_model():
    raw = json.loads(BATCH_FIXTURE.read_text(encoding="utf-8"))
    batch = CrmBatchApplyResult.model_validate(raw)
    assert batch.transport_ok is True
    assert len(batch.items) >= 1
    assert isinstance(batch.items[0], CrmApplyResult)


def test_delta_events_disabled_by_default():
    assert settings_mod.settings.PARSER_ENABLE_DELTA_EVENTS is False
    assert settings_mod.settings.SAFE_REPLAY_ALLOW_DELTA_EVENTS is False


def test_force_product_found_fallback_enabled_for_downgrade_path():
    assert settings_mod.settings.PARSER_FORCE_PRODUCT_FOUND_FALLBACK is True


def test_reconciliation_flags_present_in_settings():
    assert settings_mod.settings.PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION is True


def test_parser_sync_event_type_literal():
    ev = build_parser_sync_event_fixture()
    assert ev.event_type == "product_found"
