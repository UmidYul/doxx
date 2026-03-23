from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReadinessDomain = Literal[
    "crawl",
    "normalization",
    "crm_integration",
    "lifecycle",
    "batch_apply",
    "replay_reconciliation",
    "observability",
    "supportability",
    "security",
    "performance",
    "release_governance",
    "documentation",
]

ReadinessStatus = Literal["not_started", "partial", "ready", "blocked"]

EvidenceType = Literal[
    "unit_tests",
    "contract_tests",
    "acceptance_tests",
    "fixtures",
    "docs",
    "runbook",
    "metrics",
    "config",
    "manual_review",
]

RiskLevel = Literal["low", "medium", "high", "critical"]

ReadinessRecommendedAction = Literal["continue_build", "fix_blockers", "prepare_go_live", "not_ready"]


class ReadinessChecklistItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: ReadinessDomain
    item_code: str
    title: str
    description: str
    required: bool
    status: ReadinessStatus
    risk_if_missing: RiskLevel
    evidence_required: list[EvidenceType] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReadinessGap(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: ReadinessDomain
    gap_code: str
    description: str
    severity: RiskLevel
    blocking: bool
    recommended_next_step: str


class ReadinessEvidence(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: ReadinessDomain
    evidence_type: EvidenceType
    artifact_name: str
    artifact_path: str | None = None
    valid: bool = True
    notes: list[str] = Field(default_factory=list)


class ProductionReadinessReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    overall_status: ReadinessStatus
    domains: list[ReadinessDomain]
    checklist: list[ReadinessChecklistItem]
    gaps: list[ReadinessGap]
    evidence: list[ReadinessEvidence]
    blocking_gaps_count: int
    critical_risk_count: int
    recommended_action: ReadinessRecommendedAction
    # --- 10B: phased roadmap hints (optional; filled by enrich_readiness_with_roadmap) ---
    roadmap_summary: dict[str, object] | None = None
    roadmap_critical_path: list[str] = Field(default_factory=list)
    roadmap_phase_hints_by_domain: dict[str, str] = Field(default_factory=dict)
    roadmap_top_blocker_item_codes: list[str] = Field(default_factory=list)
    # --- 10C: go-live policy snapshot (optional) ---
    go_live_assessment_summary: dict[str, object] | None = None
    go_live_failed_exit_criteria: list[str] = Field(default_factory=list)
    go_live_blocking_cutover_items: list[str] = Field(default_factory=list)
