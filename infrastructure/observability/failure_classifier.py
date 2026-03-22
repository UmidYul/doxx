from __future__ import annotations

import re
import httpx

from domain.crm_apply_result import CrmApplyResult
from domain.observability import FailureDomain, FailureType


def classify_exception(exc: Exception) -> tuple[FailureDomain, FailureType]:
    """Map exceptions to (domain, type) for triage (store vs parser vs network vs CRM)."""
    if isinstance(exc, httpx.TimeoutException):
        return "transport", "timeout"
    if isinstance(exc, httpx.TransportError):
        return "transport", "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return classify_http_failure(exc.response.status_code, exc.response.text)
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "ban" in msg or "captcha" in msg or "blocked" in msg or "antibot" in msg:
        return "anti_bot", "block_page"
    if "parse" in name or "json" in msg or "decode" in msg:
        return "parsing", "parse_failed"
    if "reconcil" in msg:
        return "reconciliation", "reconciliation_failed"
    return "internal", "parse_failed"


def classify_http_failure(status: int | None, body: str | None = None) -> tuple[FailureDomain, FailureType]:
    """Classify HTTP-layer failures (transport vs CRM semantics)."""
    b = (body or "").lower()
    if status is None:
        return "transport", "http_error"
    if status == 408 or status == 504:
        return "transport", "timeout"
    if status == 429:
        return "transport", "http_error"
    if status >= 500:
        return "transport", "http_error"
    if status == 422 or "malformed" in b or "invalid json" in b:
        return "crm_apply", "malformed_response"
    if 400 <= status < 500:
        if "reject" in b or "validation" in b:
            return "crm_apply", "rejected_item"
        return "crm_apply", "http_error"
    return "transport", "http_error"


def classify_apply_result(result: object) -> tuple[FailureDomain | None, FailureType | None]:
    """Derive failure classification from CRM apply result (success path returns Nones)."""
    if not isinstance(result, CrmApplyResult):
        return None, None
    if result.success:
        if result.parser_reconciliation_signal == "missing_ids":
            return "crm_apply", "missing_ids"
        if result.parser_reconciliation_signal == "ambiguous_action":
            return "crm_apply", "ambiguous_result"
        return None, None
    if result.status == "ignored":
        return "crm_apply", "rejected_item"
    if result.retryable or result.status == "retryable_failure":
        return "crm_apply", "retryable_item"
    if result.status == "rejected":
        return "crm_apply", "rejected_item"
    if result.status == "transport_failure":
        return "transport", "http_error"
    return "crm_apply", "rejected_item"


def classify_normalization_issue(
    warnings: list[str],
    coverage: dict[str, object] | None = None,
) -> list[tuple[FailureDomain, FailureType]]:
    """Return one or more (domain, type) tuples from normalization warnings / coverage."""
    out: list[tuple[FailureDomain, FailureType]] = []
    wlow = [str(x).lower() for x in warnings]

    for w in wlow:
        if "partial" in w or "incomplete" in w:
            out.append(("normalization", "partial_product"))
        if "fallback" in w or "event_fallback" in w:
            out.append(("lifecycle", "event_fallback"))
        if "mapping" in w and "coverage" in w:
            out.append(("normalization", "low_mapping_coverage"))
        if "ambiguous" in w:
            out.append(("normalization", "ambiguous_result"))
        if "missing" in w and "id" in w:
            out.append(("normalization", "missing_ids"))

    ratio: float | None = None
    if coverage:
        r = coverage.get("mapping_ratio")
        if isinstance(r, (int, float)):
            ratio = float(r)
        mr = coverage.get("mapped_ratio")
        if ratio is None and isinstance(mr, (int, float)):
            ratio = float(mr)
    if ratio is not None and ratio < 0.2:
        out.append(("normalization", "low_mapping_coverage"))

    # Regex-style hints in free-text warnings
    joined = " ".join(wlow)
    if re.search(r"\blow\b.*\bcoverage\b", joined):
        out.append(("normalization", "low_mapping_coverage"))

    if not out and warnings:
        out.append(("normalization", "parse_failed"))

    # Dedupe preserving order
    seen: set[tuple[str, str]] = set()
    uniq: list[tuple[FailureDomain, FailureType]] = []
    for d, t in out:
        key = (d, t)
        if key not in seen:
            seen.add(key)
            uniq.append((d, t))
    return uniq


def classify_duplicate_skip_reason(reason: str | None) -> tuple[FailureDomain, FailureType]:
    _ = reason
    return "internal", "duplicate_payload_skipped"


def classify_malformed_batch() -> tuple[FailureDomain, FailureType]:
    return "crm_apply", "malformed_response"


def as_details_dict(exc: BaseException) -> dict[str, object]:
    return {"exception_type": type(exc).__name__, "exception_message": str(exc)[:500]}
