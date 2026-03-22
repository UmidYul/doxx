from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LayerName = Literal["config", "domain", "application", "infrastructure", "tests", "scripts"]

ViolationSeverity = Literal["warning", "high", "critical"]


class ModuleBoundaryRule(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    layer: LayerName
    allowed_dependencies: list[LayerName] = Field(default_factory=list)
    forbidden_dependencies: list[LayerName] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DependencyViolation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_module: str
    target_module: str
    violated_rule: str
    severity: ViolationSeverity
    reason: str


class CodePlacementDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    logic_name: str
    recommended_layer: LayerName
    recommended_module: str
    reason: str


class ResponsibilityArea(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    owner_layer: LayerName
    examples: list[str] = Field(default_factory=list)
    anti_examples: list[str] = Field(default_factory=list)
