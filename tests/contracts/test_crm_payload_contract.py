from __future__ import annotations

from tests.helpers.builders import build_crm_sync_item_model, build_parser_sync_event_fixture


# CRM must not silently drop these top-level sync fields
REQUIRED_CRM_SYNC_KEYS = frozenset(
    {
        "schema_version",
        "entity_key",
        "payload_hash",
        "source_name",
        "source_url",
        "title",
        "sync_mode",
        "raw_specs",
        "normalized_spec_labels",
        "compatibility_targets",
        "typed_specs",
        "normalization_warnings",
        "spec_coverage",
        "field_confidence",
        "suppressed_typed_fields",
        "normalization_quality",
        "image_urls",
        "external_ids",
        "request_idempotency_key",
    }
)

REQUIRED_PARSER_SYNC_KEYS = frozenset(
    {
        "event_id",
        "event_type",
        "sent_at",
        "identity",
        "payload_hash",
        "data",
        "request_idempotency_key",
        "replay_mode",
        "original_intent_event_type",
    }
)

REQUIRED_IDENTITY_KEYS = frozenset(
    {
        "entity_key",
        "external_ids",
        "source_name",
        "source_url",
        "source_id",
        "crm_listing_id",
        "crm_product_id",
        "barcode",
    }
)


def test_crm_sync_item_contract_stable():
    item = build_crm_sync_item_model()
    dumped = item.model_dump(mode="json")
    missing = REQUIRED_CRM_SYNC_KEYS - set(dumped)
    assert not missing, f"missing CRM sync keys: {missing}"


def test_parser_sync_event_envelope_contract_stable():
    ev = build_parser_sync_event_fixture()
    dumped = ev.model_dump(mode="json")
    missing = REQUIRED_PARSER_SYNC_KEYS - set(dumped)
    assert not missing, f"missing parser sync envelope keys: {missing}"
    ident = dumped["identity"]
    assert REQUIRED_IDENTITY_KEYS <= set(ident)


def test_batch_apply_item_contract_stable():
    from tests.helpers.builders import build_batch_apply_result_fixture

    batch = build_batch_apply_result_fixture()
    d = batch.model_dump(mode="json")
    assert set(d) >= {"items", "transport_ok", "http_status", "batch_error_code", "batch_error_message"}
    assert d["items"], "contract expects at least one sample item"
    it0 = d["items"][0]
    for k in ("event_id", "entity_key", "payload_hash", "success", "status", "parser_reconciliation_signal"):
        assert k in it0, f"missing batch item key {k}"
