from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GoLiveDecision = Literal["go", "no_go", "go_with_constraints"]

LaunchStage = Literal["pre_cutover", "cutover", "stabilization_24h", "stabilization_72h", "steady_state"]

RollbackRecommendedAction = Literal["rollback", "degrade_store", "disable_feature", "pause_store", "investigate"]


class ExitCriterion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    criterion_code: str
    title: str
    required: bool
    passed: bool
    evidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CutoverChecklistItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_code: str
    title: str
    completed: bool
    blocking: bool
    owner_role: str
    notes: list[str] = Field(default_factory=list)


class GoLiveAssessment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decision: GoLiveDecision
    launch_stage: LaunchStage
    exit_criteria: list[ExitCriterion] = Field(default_factory=list)
    cutover_checklist: list[CutoverChecklistItem] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recommended_action: str


class StabilizationCheckpoint(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    checkpoint_name: str
    time_window: Literal["0-4h", "4-24h", "24-72h"]
    checks: list[str] = Field(default_factory=list)
    passed: bool
    notes: list[str] = Field(default_factory=list)


class RollbackTrigger(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    trigger_code: str
    title: str
    severity: Literal["high", "critical"]
    condition_description: str
    recommended_action: RollbackRecommendedAction
    notes: list[str] = Field(default_factory=list)


class LaunchOutcome(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    outcome: Literal["successful", "stabilizing", "rolled_back", "degraded"]
    summary: str
    followup_actions: list[str] = Field(default_factory=list)
