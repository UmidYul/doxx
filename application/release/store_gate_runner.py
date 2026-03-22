from __future__ import annotations

from config.settings import settings
from domain.release_quality import ReleaseCheckResult

from application.qa.run_store_acceptance import run_acceptance_for_store
from application.release import release_logger as rel_log
from infrastructure.spiders.store_acceptance import get_store_acceptance_profile

# Stores with a fixture-backed runner in application.qa.run_store_acceptance
_ACCEPTANCE_RUNNERS: frozenset[str] = frozenset({"mediapark", "uzum"})


def build_store_acceptance_check(
    store_name: str,
    passed: bool,
    notes: list[str],
    *,
    artifacts: list[str] | None = None,
) -> ReleaseCheckResult:
    return ReleaseCheckResult(
        check_name=f"store_acceptance:{store_name}",
        passed=passed,
        category="acceptance",
        notes=list(notes),
        artifacts=list(artifacts or []),
    )


def run_store_acceptance_gates(store_names: list[str] | None = None) -> list[ReleaseCheckResult]:
    """Run offline fixture acceptance for each store; enabled stores from settings must pass."""
    enabled = {str(s).strip().lower() for s in settings.STORE_NAMES}
    raw_names = store_names if store_names is not None else list(enabled)
    names = [str(s).strip().lower() for s in raw_names if str(s).strip()]
    results: list[ReleaseCheckResult] = []
    for name in names:
        if name not in enabled:
            continue
        if name not in _ACCEPTANCE_RUNNERS:
            r = build_store_acceptance_check(
                name,
                False,
                [f"no fixture acceptance runner for {name!r} — add scenarios to run_store_acceptance + store_acceptance registry"],
            )
            results.append(r)
            rel_log.emit_store_acceptance_failed(store_name=name, notes=r.notes)
            rel_log.emit_release_check_failed(check_name=r.check_name, category="acceptance", notes=r.notes)
            continue
        _ = get_store_acceptance_profile(name)
        try:
            report, summary = run_acceptance_for_store(name)
            passed = bool(report.get("quality_gate_passed"))
            notes: list[str] = [] if passed else [f"quality_gate_passed=false", str(summary)]
        except AssertionError as e:
            passed = False
            notes = [str(e)]
        r = build_store_acceptance_check(name, passed, notes, artifacts=[f"fixtures:tests/fixtures/stores/{name}/"])
        results.append(r)
        if passed:
            rel_log.emit_release_check_passed(check_name=r.check_name, category="acceptance")
        else:
            rel_log.emit_store_acceptance_failed(store_name=name, notes=notes)
            rel_log.emit_release_check_failed(check_name=r.check_name, category="acceptance", notes=notes)
    return results
