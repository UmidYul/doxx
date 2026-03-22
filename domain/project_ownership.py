from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeAssetType = Literal["doc", "adr", "runbook", "playbook", "workflow", "fixture_guide"]


class OwnershipArea(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str
    modules: list[str] = Field(default_factory=list)


class ModuleOwnerRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ownership_area: str
    primary_owner_role: str
    secondary_owner_role: str | None = None
    escalation_path: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class SupportOwnershipRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str
    owner_role: str
    fallback_role: str | None = None
    notes: list[str] = Field(default_factory=list)


class KnowledgeAsset(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    asset_name: str
    asset_type: KnowledgeAssetType
    path: str
    purpose: str
