from __future__ import annotations

import httpx
import pytest

from domain.crm_apply_result import CrmApplyResult

from infrastructure.observability.failure_classifier import (
    classify_apply_result,
    classify_exception,
    classify_http_failure,
    classify_normalization_issue,
)


def test_classify_http_transport_vs_malformed():
    d1, t1 = classify_http_failure(500, "internal error")
    assert d1 == "transport"
    assert t1 == "http_error"

    d2, t2 = classify_http_failure(422, "malformed json payload")
    assert d2 == "crm_apply"
    assert t2 == "malformed_response"


def test_classify_exception_timeout():
    d, t = classify_exception(httpx.TimeoutException("timeout"))
    assert d == "transport"
    assert t == "timeout"


def test_classify_apply_result_retryable_vs_rejected():
    r_ok = CrmApplyResult(
        event_id="e",
        entity_key="k",
        payload_hash="h",
        success=True,
        status="applied",
    )
    assert classify_apply_result(r_ok) == (None, None)

    r_retry = CrmApplyResult(
        event_id="e",
        entity_key="k",
        payload_hash="h",
        success=False,
        status="retryable_failure",
        retryable=True,
    )
    d, t = classify_apply_result(r_retry)
    assert d == "crm_apply"
    assert t == "retryable_item"

    r_rej = CrmApplyResult(
        event_id="e",
        entity_key="k",
        payload_hash="h",
        success=False,
        status="rejected",
        retryable=False,
    )
    d2, t2 = classify_apply_result(r_rej)
    assert d2 == "crm_apply"
    assert t2 == "rejected_item"


def test_classify_normalization_low_coverage_distinct():
    pairs = classify_normalization_issue([], coverage={"mapping_ratio": 0.01})
    assert ("normalization", "low_mapping_coverage") in pairs


@pytest.mark.parametrize(
    ("sig", "ftype"),
    [
        ("missing_ids", "missing_ids"),
        ("ambiguous_action", "ambiguous_result"),
    ],
)
def test_classify_apply_result_reconciliation_signals(sig: str, ftype: str):
    r = CrmApplyResult(
        event_id="e",
        entity_key="k",
        payload_hash="h",
        success=True,
        status="applied",
        parser_reconciliation_signal=sig,
    )
    d, t = classify_apply_result(r)
    assert d == "crm_apply"
    assert t == ftype
