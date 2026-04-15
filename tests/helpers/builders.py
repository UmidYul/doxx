from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult
from domain.crm_lifecycle import CrmIdentityContext
from domain.crm_sync import CrmSyncItem
from domain.parser_event import ParserSyncEvent


def build_normalized_item_fixture(
    *,
    store: str = "mediapark",
    source_id: str = "fixture-1",
    category_hint: str = "phone",
) -> dict[str, Any]:
    """Typical hybrid-normalized dict shape (pre–CRM sync builder)."""
    return {
        "source_name": store,
        "source_url": f"https://{store}.uz/p/{source_id}",
        "source_id": source_id,
        "external_ids": {store: source_id},
        "title": "Fixture phone",
        "brand": "FixtureBrand",
        "category_hint": category_hint,
        "price_value": 1000,
        "price_raw": "1000 сум",
        "currency": "UZS",
        "in_stock": True,
        "raw_specs": {"оперативная память": "8 GB"},
        "typed_specs": {"ram_gb": 8},
        "normalization_warnings": [],
        "spec_coverage": {"mapping_ratio": 0.5},
        "field_confidence": {},
        "suppressed_typed_fields": [],
        "normalization_quality": {},
        "description": None,
        "image_urls": [],
        "barcode": None,
        "model_name": "FB-1",
    }


def build_crm_sync_item_model(**overrides: Any) -> CrmSyncItem:
    base = dict(
        schema_version=1,
        entity_key="mediapark:fixture-1",
        payload_hash="sha256:" + "a" * 64,
        source_name="mediapark",
        source_url="https://mediapark.uz/p/fixture-1",
        source_id="fixture-1",
        external_ids={"mediapark": "fixture-1"},
        title="Fixture",
        brand="B",
        category_hint="phone",
        price_value=1,
        price_raw="1",
        currency="UZS",
        in_stock=True,
        raw_specs={},
        normalized_spec_labels={},
        compatibility_targets=[],
        typed_specs={},
        normalization_warnings=[],
        spec_coverage={},
        field_confidence={},
        suppressed_typed_fields=[],
        normalization_quality={},
        description=None,
        image_urls=[],
        scraped_at=datetime(2020, 1, 1, tzinfo=UTC),
        barcode=None,
        model_name=None,
        sync_mode="snapshot",
        change_hint=None,
        request_idempotency_key="idem-fixture",
    )
    base.update(overrides)
    return CrmSyncItem(**base)


def build_parser_sync_event_fixture(**overrides: Any) -> ParserSyncEvent:
    data = build_crm_sync_item_model()
    ident = CrmIdentityContext(
        entity_key=data.entity_key,
        external_ids=dict(data.external_ids),
        barcode=data.barcode,
        source_name=data.source_name,
        source_url=data.source_url,
        source_id=data.source_id,
        crm_listing_id=None,
        crm_product_id=None,
    )
    ev = ParserSyncEvent(
        event_id="00000000-0000-4000-8000-000000000001",
        event_type="product_found",
        sent_at=datetime(2020, 1, 1, tzinfo=UTC),
        identity=ident,
        payload_hash=data.payload_hash,
        data=data,
        request_idempotency_key="idem-fixture",
        replay_mode="snapshot_upsert",
        original_intent_event_type=None,
    )
    if overrides:
        return ev.model_copy(update=overrides)
    return ev


def build_crm_apply_result_fixture(**overrides: Any) -> CrmApplyResult:
    base = dict(
        event_id="00000000-0000-4000-8000-000000000001",
        entity_key="mediapark:1",
        payload_hash="sha256:" + "b" * 64,
        success=True,
        status="applied",
        http_status=200,
        action="upsert",
        crm_listing_id="L1",
        crm_product_id="P1",
        retryable=False,
        error_code=None,
        error_message=None,
        parser_reconciliation_signal=None,
    )
    base.update(overrides)
    return CrmApplyResult(**base)


def build_batch_apply_result_fixture(
    items: list[CrmApplyResult] | None = None,
    **overrides: Any,
) -> CrmBatchApplyResult:
    batch = CrmBatchApplyResult(
        items=items or [build_crm_apply_result_fixture()],
        transport_ok=True,
        http_status=200,
        batch_error_code=None,
        batch_error_message=None,
    )
    if overrides:
        return batch.model_copy(update=overrides)
    return batch


def build_etl_status_fixture(**overrides: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema": "parser_etl_status_v3",
        "run_id": "fixture-run",
        "current_status": "healthy",
        "operator_support": {},
        "triage_summary": {},
        "diagnostic_snapshot": {},
        "dashboard_summary": {},
    }
    d.update(overrides)
    return d


def build_store_operational_snapshot() -> dict[str, Any]:
    return {"overall_status": "healthy", "per_store_status": {"mediapark": "healthy"}}
