from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RolloutStage = Literal["disabled", "canary", "partial", "full"]

RolloutScope = Literal["global", "store", "feature", "store_feature"]


class FeatureFlagState(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    feature_name: str
    stage: RolloutStage
    enabled: bool
    rollout_percentage: int | None = None
    allowed_stores: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StoreRolloutState(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    enabled: bool
    stage: RolloutStage
    canary: bool = False
    feature_overrides: dict[str, RolloutStage] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RolloutDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    feature_name: str
    store_name: str | None
    stage: RolloutStage
    enabled: bool
    reason: str | None = None
    canary_selected: bool
    rollout_scope: RolloutScope


class RollbackDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    should_rollback: bool
    target_scope: RolloutScope
    target_name: str | None = None
    reason: str
    recommended_stage: RolloutStage
