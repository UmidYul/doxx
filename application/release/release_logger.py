from __future__ import annotations

from config.settings import settings
from infrastructure.observability import message_codes as omc


def _emit(
    message_code: str,
    *,
    check_name: str | None = None,
    category: str | None = None,
    gate_name: str | None = None,
    severity: str | None = None,
    passed: bool | None = None,
    store_name: str | None = None,
    recommended_action: str | None = None,
    artifact: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    if not getattr(settings, "ENABLE_RELEASE_QUALITY_LOGS", False):
        return
    from infrastructure.observability.operational_logger import emit_operational_event

    payload = dict(details or {})
    if check_name is not None:
        payload["check_name"] = check_name
    if category is not None:
        payload["category"] = category
    if gate_name is not None:
        payload["gate_name"] = gate_name
    if severity is not None:
        payload["severity"] = severity
    if passed is not None:
        payload["passed"] = passed
    if store_name is not None:
        payload["store_name"] = store_name
    if recommended_action is not None:
        payload["recommended_action"] = recommended_action
    if artifact is not None:
        payload["artifact"] = artifact
    emit_operational_event(
        message_code,
        run_id="release_quality",
        severity=severity,
        recommended_action=recommended_action,
        details=payload,
    )


def emit_release_gate_evaluated(*, gate_name: str, passed: bool, severity: str, details: list[str]) -> None:
    _emit(
        omc.RELEASE_GATE_EVALUATED,
        gate_name=gate_name,
        passed=passed,
        severity=severity,
        details={"lines": details},
    )


def emit_release_check_passed(*, check_name: str, category: str) -> None:
    _emit(omc.RELEASE_CHECK_PASSED, check_name=check_name, category=category, passed=True)


def emit_release_check_failed(*, check_name: str, category: str, notes: list[str]) -> None:
    _emit(omc.RELEASE_CHECK_FAILED, check_name=check_name, category=category, passed=False, details={"notes": notes})


def emit_contract_drift(*, check_name: str, notes: list[str]) -> None:
    _emit(
        omc.CONTRACT_DRIFT_DETECTED,
        check_name=check_name,
        category="contract",
        severity="critical",
        passed=False,
        details={"notes": notes},
    )


def emit_store_acceptance_failed(*, store_name: str, notes: list[str]) -> None:
    _emit(
        omc.STORE_ACCEPTANCE_GATE_FAILED,
        store_name=store_name,
        severity="critical",
        passed=False,
        details={"notes": notes},
    )


def emit_release_ready() -> None:
    _emit(omc.RELEASE_READY, passed=True, severity="info", recommended_action="release")


def emit_release_blocked(*, reason: str, critical_failures: int) -> None:
    _emit(
        omc.RELEASE_BLOCKED,
        passed=False,
        severity="critical",
        recommended_action="block_release",
        details={"reason": reason, "critical_failures": critical_failures},
    )
