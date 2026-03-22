from __future__ import annotations

from typing import Any

from config.settings import settings
from domain.crm_apply_result import (
    CrmApplyResult,
    CrmApplyStatus,
    CrmBatchApplyResult,
    MalformedCrmBatchResponse,
)
from domain.parser_event import ParserSyncEvent


def is_retryable_http_status(status: int | None) -> bool:
    if status is None:
        return False
    return status == 429 or status >= 500


def is_business_rejection(status: int | None, error_code: str | None = None) -> bool:
    if status is not None and status in (400, 401, 403, 404, 422):
        return True
    ec = (error_code or "").upper()
    return ec in ("VALIDATION_ERROR", "REJECTED", "FORBIDDEN", "UNAUTHORIZED")


def _row_looks_success(row: dict[str, Any]) -> bool:
    if row.get("success") is True:
        return True
    st = row.get("status")
    if st is True:
        return True
    if isinstance(st, str) and st.lower() in ("ok", "success", "synced", "created", "updated", "matched", "applied"):
        return True
    if isinstance(st, int) and 200 <= st < 300:
        return True
    return False


def _row_retryable_row(row: dict[str, Any], http_status: int) -> bool:
    if row.get("retryable") is True:
        return True
    ec = str(row.get("error_code") or "").upper()
    if ec in ("RATE_LIMIT", "SERVICE_UNAVAILABLE", "TIMEOUT", "TEMPORARY"):
        return True
    return is_retryable_http_status(http_status)


def _normalize_action(action: object | None) -> str | None:
    if action is None:
        return None
    s = str(action).strip()
    return s or None


def _status_from_action(action: str | None, row_ok: bool) -> CrmApplyStatus:
    if not row_ok:
        return "rejected"
    a = (action or "").lower()
    if a == "created":
        return "created"
    if a in ("matched", "needs_review"):
        return "matched"
    if a == "updated":
        return "updated"
    if a == "ignored":
        return "ignored"
    if a in ("applied", ""):
        return "applied"
    return "applied"


def _extract_batch_rows(response_json: Any, n: int) -> list[dict[str, Any] | None]:
    if response_json is None:
        return [None] * n
    if isinstance(response_json, list):
        rows: list[dict[str, Any] | None] = [r if isinstance(r, dict) else None for r in response_json]
        while len(rows) < n:
            rows.append(None)
        return rows[:n]
    if isinstance(response_json, dict):
        inner = response_json.get("results")
        if isinstance(inner, list):
            rows = [r if isinstance(r, dict) else None for r in inner]
            while len(rows) < n:
                rows.append(None)
            return rows[:n]
        if n == 1:
            return [response_json]
        return [None] * n
    return [None] * n


def _row_to_apply_result(
    event: ParserSyncEvent,
    http_status: int,
    row: dict[str, Any] | None,
    *,
    force_transport_failure: bool = False,
) -> CrmApplyResult:
    ek = event.data.entity_key
    ph = event.data.payload_hash
    eid = event.event_id

    if force_transport_failure:
        return CrmApplyResult(
            event_id=eid,
            entity_key=ek,
            payload_hash=ph,
            success=False,
            status="transport_failure",
            http_status=http_status,
            retryable=False,
            error_code="missing_item_result",
            error_message="missing_or_malformed_item_result",
        )

    if row is None:
        retryable = is_retryable_http_status(http_status)
        st: CrmApplyStatus = "retryable_failure" if retryable else "transport_failure"
        if http_status >= 400 and not retryable:
            st = "rejected" if is_business_rejection(http_status) else "transport_failure"
        return CrmApplyResult(
            event_id=eid,
            entity_key=ek,
            payload_hash=ph,
            success=False,
            status=st,
            http_status=http_status,
            retryable=retryable and st == "retryable_failure",
            error_code=str(http_status) if http_status else "http_error",
            error_message=f"http_{http_status}",
        )

    ok = _row_looks_success(row)
    listing = row.get("crm_listing_id") or row.get("listing_id")
    product = row.get("crm_product_id") or row.get("product_id")
    action = _normalize_action(row.get("action"))
    err_c = row.get("error_code")
    if err_c is not None:
        err_c = str(err_c)
    err_m = row.get("error_message") or row.get("error") or row.get("detail")
    if err_m is not None:
        err_m = str(err_m)

    if ok:
        st = _status_from_action(action, True)
        success = True
        if (action or "").lower() == "ignored" and not settings.PARSER_MARK_IGNORED_AS_APPLIED:
            success = False
        retryable = False
        parser_sig: str | None = None
        if success:
            evt_t = event.event_type
            has_l = listing is not None and str(listing).strip() != ""
            has_p = product is not None and str(product).strip() != ""
            if evt_t == "product_found" and not has_l and not has_p and settings.PARSER_RECONCILE_ON_MISSING_IDS:
                parser_sig = "missing_ids"
            act_l = (action or "").lower()
            if act_l == "needs_review" and settings.PARSER_RECONCILE_ON_AMBIGUOUS_RESULT:
                parser_sig = "ambiguous_action" if parser_sig is None else parser_sig
        return CrmApplyResult(
            event_id=eid,
            entity_key=ek,
            payload_hash=ph,
            success=success,
            status=st,
            http_status=http_status,
            action=action,
            crm_listing_id=str(listing) if listing is not None else None,
            crm_product_id=str(product) if product is not None else None,
            retryable=retryable,
            error_code=err_c,
            error_message=err_m,
            parser_reconciliation_signal=parser_sig,
        )

    retryable = _row_retryable_row(row, http_status)
    if retryable:
        st = "retryable_failure"
    elif http_status is not None and http_status >= 400:
        st = "rejected" if is_business_rejection(http_status, err_c) else "transport_failure"
    else:
        # Parsed per-item row under 2xx envelope — CRM business outcome failed.
        st = "rejected"

    return CrmApplyResult(
        event_id=eid,
        entity_key=ek,
        payload_hash=ph,
        success=False,
        status=st,
        http_status=http_status,
        action=action,
        crm_listing_id=str(listing) if listing is not None else None,
        crm_product_id=str(product) if product is not None else None,
        retryable=retryable,
        error_code=err_c,
        error_message=err_m,
    )


def classify_single_sync_response(
    event: ParserSyncEvent,
    http_status: int,
    response_json: dict[str, Any] | None,
) -> CrmApplyResult:
    """Classify one CRM ``/api/parser/sync`` response (HTTP + JSON body)."""
    if http_status >= 400:
        retryable = is_retryable_http_status(http_status)
        st: CrmApplyStatus = "retryable_failure" if retryable else "rejected"
        if http_status >= 500:
            st = "retryable_failure"
        return CrmApplyResult(
            event_id=event.event_id,
            entity_key=event.data.entity_key,
            payload_hash=event.data.payload_hash,
            success=False,
            status=st,
            http_status=http_status,
            retryable=retryable,
            error_code=str(http_status),
            error_message=f"http_{http_status}",
        )

    row: dict[str, Any] | None
    if response_json is None:
        row = None
    elif isinstance(response_json, list) and response_json and isinstance(response_json[0], dict):
        row = response_json[0]
    elif isinstance(response_json, dict):
        if response_json.get("results") is not None and isinstance(response_json.get("results"), list):
            inner = response_json["results"]
            row = inner[0] if inner and isinstance(inner[0], dict) else None
        else:
            row = response_json
    else:
        row = None

    return _row_to_apply_result(event, http_status, row)


def classify_batch_sync_response(
    events: list[ParserSyncEvent],
    http_status: int,
    response_json: dict[str, Any] | list[Any] | None,
) -> CrmBatchApplyResult:
    """Classify batch CRM response into per-item :class:`CrmApplyResult` rows."""
    n = len(events)
    if n == 0:
        return CrmBatchApplyResult(items=[], transport_ok=True, http_status=http_status)

    if http_status >= 400:
        retryable = is_retryable_http_status(http_status)
        st: CrmApplyStatus = "retryable_failure" if retryable else "rejected"
        if http_status >= 500:
            st = "retryable_failure"
        items = [
            CrmApplyResult(
                event_id=e.event_id,
                entity_key=e.data.entity_key,
                payload_hash=e.data.payload_hash,
                success=False,
                status=st,
                http_status=http_status,
                retryable=retryable,
                error_code=str(http_status),
                error_message=f"batch_http_{http_status}",
            )
            for e in events
        ]
        return CrmBatchApplyResult(
            items=items,
            transport_ok=False,
            http_status=http_status,
            batch_error_code=str(http_status),
            batch_error_message=f"batch_http_{http_status}",
        )

    rows = _extract_batch_rows(response_json, n)
    if settings.CRM_BATCH_REQUIRE_ITEM_RESULTS:
        malformed = len(rows) != n or any(r is None for r in rows)
        if malformed:
            synth = CrmBatchApplyResult(
                items=[
                    _row_to_apply_result(events[i], http_status, None, force_transport_failure=True)
                    for i in range(n)
                ],
                transport_ok=False,
                http_status=http_status,
                batch_error_code="malformed_batch_response",
                batch_error_message="missing_or_mismatched_item_results",
            )
            if settings.CRM_BATCH_STOP_ON_MALFORMED_RESPONSE:
                raise MalformedCrmBatchResponse("batch response missing per-item results", batch=synth)
            return synth

    items = [_row_to_apply_result(events[i], http_status, rows[i]) for i in range(n)]
    return CrmBatchApplyResult(
        items=items,
        transport_ok=http_status < 400,
        http_status=http_status,
    )
