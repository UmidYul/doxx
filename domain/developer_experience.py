from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DevRunMode = Literal["normal", "dry_run", "debug", "fixture_replay", "acceptance"]


class DevCommandDescriptor(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    purpose: str
    example: str
    notes: list[str] = Field(default_factory=list)


class DebugView(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    section_name: str
    included_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FixtureReplayPlan(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fixture_name: str
    store_name: str | None = None
    mode: DevRunMode = "fixture_replay"
    steps: list[str] = Field(default_factory=list)
