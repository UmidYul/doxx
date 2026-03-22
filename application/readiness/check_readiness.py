from __future__ import annotations

import sys
from pathlib import Path

from application.readiness.evidence_collector import collect_readiness_evidence
from application.readiness.gap_assessor import assess_readiness_gaps, infer_blocking_gaps, update_checklist_status_from_evidence
from application.readiness.readiness_registry import get_default_readiness_checklist
from application.readiness.readiness_report import (
    build_human_readiness_report,
    build_production_readiness_report,
    compute_readiness_gate_flags,
)


def main(argv: list[str] | None = None) -> int:
    """Run readiness assessment; exit 1 if blocking gaps exist."""
    args = list(argv if argv is not None else sys.argv[1:])
    root = str(Path(args[0]).resolve()) if args else str(Path(__file__).resolve().parents[2])

    evidence = collect_readiness_evidence(root)
    checklist = update_checklist_status_from_evidence(get_default_readiness_checklist(), evidence, root)
    gaps = assess_readiness_gaps(checklist, evidence)
    report = build_production_readiness_report(checklist, gaps, evidence)

    print(build_human_readiness_report(report))  # noqa: T201

    flags = compute_readiness_gate_flags(root, emit_structured_logs=False)
    print("\nRelease gate flags:", flags)  # noqa: T201

    blocking = infer_blocking_gaps(gaps)
    if blocking or report.overall_status == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
