from __future__ import annotations

from config.settings import settings
from domain.go_live import ExitCriterion
from domain.production_readiness import ProductionReadinessReport
from domain.release_quality import ReleaseReadinessSummary


def get_default_exit_criteria() -> list[ExitCriterion]:
    """Canonical exit criteria catalog (evaluated separately)."""
    return [
        ExitCriterion(
            criterion_code="exit.readiness_not_blocked",
            title="Readiness overall not blocked; blocking gaps closed per policy",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.release_gates_clean",
            title="No critical release gate failures; release summary allows ship",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.crm_payload_lifecycle_clean",
            title="CRM payload / lifecycle compatibility checks clean",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.security_baseline",
            title="Security baseline validated (startup validation, redaction, outbound guards)",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.observability_etl",
            title="Observability baseline + ETL/status export available",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.rollout_policy_present",
            title="Rollout policy configured for progressive enablement",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.store_acceptance",
            title="Enabled stores have acceptance evidence / no failing acceptance checks",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.store_playbooks",
            title="Enabled stores have playbooks/runbooks on disk",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.dry_run_smoke_contract",
            title="Dry-run, smoke, and contract checks pass for cutover scope",
            required=True,
            passed=False,
        ),
        ExitCriterion(
            criterion_code="exit.canary_scope_first_launch",
            title="First production launch limited to canary / approved stores only",
            required=True,
            passed=False,
        ),
    ]


def get_required_exit_criteria() -> list[ExitCriterion]:
    return [c for c in get_default_exit_criteria() if c.required]


def evaluate_exit_criteria(
    readiness_report: ProductionReadinessReport,
    release_summary: ReleaseReadinessSummary | None,
    statuses: dict[str, object] | None,
    docs_coverage: dict[str, object] | None,
) -> list[ExitCriterion]:
    """Set passed/evidence on each criterion from readiness, release, ops signals, docs."""
    st = statuses or {}
    doc = docs_coverage or {}
    out: list[ExitCriterion] = []

    def _bool(key: str, default: bool = False) -> bool:
        v = st.get(key)
        if isinstance(v, bool):
            return v
        return default

    for c in get_default_exit_criteria():
        passed = False
        evidence: list[str] = []
        notes: list[str] = []

        if c.criterion_code == "exit.readiness_not_blocked":
            need_ready = getattr(settings, "GO_LIVE_REQUIRE_READINESS_READY", True)
            base_ok = (
                readiness_report.overall_status != "blocked"
                and readiness_report.blocking_gaps_count == 0
            )
            passed = base_ok and (readiness_report.overall_status == "ready" if need_ready else True)
            evidence.append(f"overall_status={readiness_report.overall_status} blocking_gaps={readiness_report.blocking_gaps_count}")

        elif c.criterion_code == "exit.release_gates_clean":
            if not getattr(settings, "GO_LIVE_REQUIRE_RELEASE_GATES_PASS", True):
                passed = True
                evidence.append("release_gate_check_disabled_by_settings")
            elif release_summary is None:
                passed = False
                notes.append("No release summary supplied; cannot verify gates.")
            else:
                passed = bool(
                    release_summary.overall_passed
                    and release_summary.critical_failures == 0
                    and release_summary.recommended_action != "block_release"
                )
                evidence.append(
                    f"overall_passed={release_summary.overall_passed} "
                    f"critical_failures={release_summary.critical_failures} action={release_summary.recommended_action}"
                )

        elif c.criterion_code == "exit.crm_payload_lifecycle_clean":
            watch = ("crm.payload_contract", "life.lifecycle_tests")
            relevant = [i for i in readiness_report.checklist if i.item_code in watch]
            if relevant:
                passed = all(i.status == "ready" for i in relevant)
            else:
                passed = _bool("crm_contract_checks_pass", False) and _bool("lifecycle_compatibility_clean", False)
            evidence.append("crm_payload_lifecycle_evaluated")

        elif c.criterion_code == "exit.security_baseline":
            if not getattr(settings, "GO_LIVE_REQUIRE_SECURITY_BASELINE", True):
                passed = True
                evidence.append("security_baseline_not_required_by_settings")
            else:
                sec_items = [i for i in readiness_report.checklist if i.domain == "security" and i.required]
                passed = all(i.status == "ready" for i in sec_items) if sec_items else _bool("security_baseline_validated", False)
                evidence.append(f"security_required_items_ready={passed}")

        elif c.criterion_code == "exit.observability_etl":
            if not getattr(settings, "GO_LIVE_REQUIRE_OBSERVABILITY_BASELINE", True):
                passed = True
            else:
                obs = [i for i in readiness_report.checklist if i.domain == "observability" and i.required]
                passed = all(i.status == "ready" for i in obs) if obs else _bool("observability_baseline_ok", False)
                etl = bool(getattr(settings, "ENABLE_ETL_STATUS_EXPORT", True))
                passed = passed and etl
                evidence.append(f"etl_export_enabled={etl}")

        elif c.criterion_code == "exit.rollout_policy_present":
            if not getattr(settings, "GO_LIVE_REQUIRE_ROLLOUT_POLICY", True):
                passed = True
            else:
                rel = [i for i in readiness_report.checklist if i.item_code == "rel.rollout_policy"]
                passed = (rel[0].status == "ready" if rel else False) or _bool("rollout_policy_configured", False)
                evidence.append("rollout_policy_checklist_or_status")

        elif c.criterion_code == "exit.store_acceptance":
            failed_acceptance = []
            if release_summary and release_summary.checks:
                failed_acceptance = [
                    x.check_name for x in release_summary.checks if not x.passed and x.category == "acceptance"
                ]
            passed = len(failed_acceptance) == 0 and _bool("store_acceptance_complete", True)
            if failed_acceptance:
                notes.append(f"acceptance_failures={failed_acceptance}")

        elif c.criterion_code == "exit.store_playbooks":
            if not getattr(settings, "GO_LIVE_REQUIRE_ENABLED_STORE_PLAYBOOKS", True):
                passed = True
            else:
                enabled = list(doc.get("enabled_stores") or [])
                missing = list(doc.get("missing_playbooks") or [])
                if doc.get("all_playbooks_present") is True:
                    passed = True
                elif enabled:
                    passed = len(missing) == 0
                else:
                    passed = _bool("store_playbooks_ok", False)
                evidence.append(f"enabled={enabled} missing={missing}")

        elif c.criterion_code == "exit.dry_run_smoke_contract":
            dry = _bool("dry_run_passed", False)
            smoke = _bool("smoke_passed", False)
            contract = _bool("contract_checks_passed", False)
            passed = dry and smoke and contract
            evidence.append(f"dry={dry} smoke={smoke} contract={contract}")

        elif c.criterion_code == "exit.canary_scope_first_launch":
            if not getattr(settings, "GO_LIVE_CANARY_ONLY_FIRST", True):
                passed = True
                evidence.append("canary_only_first_disabled")
            else:
                violation = bool(st.get("full_rollout_without_canary_violation", False))
                canary_ok = _bool("canary_scope_confirmed", False)
                passed = canary_ok and not violation
                if violation:
                    notes.append("Enabled store(s) not on canary for first launch.")

        out.append(
            c.model_copy(
                update={"passed": passed, "evidence": evidence, "notes": notes},
            )
        )
    return out
