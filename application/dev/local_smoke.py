from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from config.settings import settings
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_developer_experience_event


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _release_baseline_passing() -> dict[str, object]:
    return {
        "critical_unit_tests_passed": True,
        "contract_tests_passed": True,
        "store_acceptance_passed": True,
        "payload_compatibility_passed": True,
        "lifecycle_replay_safety_passed": True,
        "malformed_response_regression_ok": True,
        "mapping_coverage_regression_ok": True,
        "parse_success_golden_ok": True,
        "compatibility_core_surfaces_clean": True,
        "compatibility_no_unplanned_breaking": True,
        "migration_readiness_acceptable": True,
        "deprecation_removal_safe": True,
        "dual_shape_plan_when_needed": True,
        "cost_perf_regression_gate_ok": True,
        "store_efficiency_policy_ok": True,
        "arch_dependency_gate_ok": True,
        "arch_anti_pattern_gate_ok": True,
        "architecture_lint_report_ok": True,
        "arch_core_import_gate_ok": True,
        "docs_required_present": True,
        "store_playbooks_for_enabled_stores": True,
        "crm_integration_release_support_docs_present": True,
        "docs_coverage_acceptable": True,
        "knowledge_continuity_no_critical_gaps": True,
        "readiness_no_critical_blocking_gaps": True,
        "readiness_required_domains_not_blocked": True,
        "readiness_report_available": True,
        "readiness_enabled_stores_have_evidence": True,
        "readiness_critical_evidence_security_crm_release": True,
    }


def run_local_smoke() -> dict[str, object]:
    """Fast layered smoke check for local DX (9B)."""
    from infrastructure.security.startup_guard import reset_startup_security_checks_for_tests

    reset_startup_security_checks_for_tests()

    steps: list[dict[str, Any]] = []
    ok_all = True

    try:
        _ = settings.TRANSPORT_TYPE
        steps.append({"step": "config_load", "pass": True})
    except Exception as e:
        ok_all = False
        steps.append({"step": "config_load", "pass": False, "error": str(e)})

    try:
        from infrastructure.security.startup_guard import run_startup_security_checks

        cfg = settings.model_copy(update={"ENABLE_SECURITY_STARTUP_VALIDATION": False})
        r = run_startup_security_checks(cfg, force=True)
        steps.append(
            {
                "step": "security_startup",
                "pass": bool(r.passed),
                "note": "validation disabled for smoke portability; enable in real runs",
            }
        )
        ok_all = ok_all and r.passed
    except Exception as e:
        ok_all = False
        steps.append({"step": "security_startup", "pass": False, "error": str(e)})

    try:
        from application.release.release_gate_evaluator import evaluate_release_gates

        gates = evaluate_release_gates(_release_baseline_passing())
        passed = all(g.passed for g in gates)
        steps.append({"step": "release_gates_baseline", "pass": passed, "gate_count": len(gates)})
        ok_all = ok_all and passed
    except Exception as e:
        ok_all = False
        steps.append({"step": "release_gates_baseline", "pass": False, "error": str(e)})

    laptop = _repo_root() / "tests" / "fixtures" / "regression" / "normalization" / "laptop.json"
    try:
        from application.dev.fixture_replay import replay_lifecycle_fixture, replay_normalization_fixture

        n_out = replay_normalization_fixture(str(laptop))
        steps.append({"step": "fixture_normalization", "pass": "normalized" in n_out})
        ok_all = ok_all and bool(n_out.get("normalized"))

        l_out = replay_lifecycle_fixture(str(laptop))
        steps.append({"step": "lifecycle_build", "pass": "lifecycle_event" in l_out})
        ok_all = ok_all and bool(l_out.get("lifecycle_event"))
    except Exception as e:
        ok_all = False
        steps.append({"step": "fixture_normalization_or_lifecycle", "pass": False, "error": str(e)})

    try:
        from infrastructure.transports.dry_run import DryRunTransport
        from infrastructure.transports.factory import get_transport

        with patch.multiple(
            "infrastructure.transports.factory.settings",
            MOSCRAPER_DISABLE_PUBLISH=False,
            TRANSPORT_TYPE="crm_http",
            DEV_MODE=True,
            DEV_DRY_RUN_DISABLE_CRM_SEND=True,
        ):
            t = get_transport()
        steps.append({"step": "transport_dry_run", "pass": isinstance(t, DryRunTransport)})
        ok_all = ok_all and isinstance(t, DryRunTransport)
    except Exception as e:
        ok_all = False
        steps.append({"step": "transport_dry_run", "pass": False, "error": str(e)})

    log_developer_experience_event(
        obs_mc.DEV_LOCAL_SMOKE_COMPLETED,
        dev_run_mode=getattr(settings, "DEV_RUN_MODE", "normal"),
        pass_ok=ok_all,
        items_count=len(steps),
        sections_included=[str(s.get("step")) for s in steps],
        details={"steps": steps},
    )
    return {"pass": ok_all, "steps": steps}


def main(argv: list[str] | None = None) -> int:
    """CLI entry for ``python -m application.dev.local_smoke``."""
    r = run_local_smoke()
    print(r)  # noqa: T201
    return 0 if r.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
