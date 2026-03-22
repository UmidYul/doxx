from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoadmapPhase = Literal["foundation", "go_live_baseline", "post_launch_hardening", "scale_maturity"]

PriorityLevel = Literal["p0", "p1", "p2", "p3"]

Workstream = Literal[
    "crawl",
    "normalization",
    "crm_integration",
    "lifecycle",
    "observability",
    "security",
    "performance",
    "release_governance",
    "documentation",
    "support",
]

EffortLevel = Literal["small", "medium", "large"]


class RoadmapItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_code: str
    title: str
    workstream: Workstream
    phase: RoadmapPhase
    priority: PriorityLevel
    depends_on: list[str] = Field(default_factory=list)
    blocking_for_go_live: bool
    recommended_owner_area: str
    effort: EffortLevel = "medium"
    notes: list[str] = Field(default_factory=list)


class PhasePlan(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phase: RoadmapPhase
    goals: list[str] = Field(default_factory=list)
    items: list[RoadmapItem] = Field(default_factory=list)
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)


class RoadmapDependency(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    from_item_code: str
    to_item_code: str
    reason: str


class ImplementationRoadmap(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phases: list[PhasePlan] = Field(default_factory=list)
    dependencies: list[RoadmapDependency] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    go_live_blockers: list[str] = Field(default_factory=list)
    post_launch_items: list[str] = Field(default_factory=list)
