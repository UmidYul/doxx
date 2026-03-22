"""Production readiness assessment (10A): checklist, evidence, gaps, report."""

from __future__ import annotations

from application.readiness.check_readiness import main as check_readiness_main
from application.readiness.evidence_collector import collect_readiness_evidence
from application.readiness.readiness_registry import get_default_readiness_checklist
from application.readiness.readiness_report import compute_readiness_gate_flags

__all__ = [
    "check_readiness_main",
    "collect_readiness_evidence",
    "compute_readiness_gate_flags",
    "get_default_readiness_checklist",
]
