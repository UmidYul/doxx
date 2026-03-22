from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NetworkMode = Literal["open", "restricted"]
OutboundTargetType = Literal["store", "crm", "proxy", "unknown"]


class HostValidationDecision(BaseModel):
    allowed: bool
    target_type: OutboundTargetType
    host: str
    reason: str | None = None
    matched_rule: str | None = None


class RedirectDecision(BaseModel):
    allowed: bool
    from_url: str
    to_url: str
    reason: str | None = None
    same_site: bool


class ProxySecurityDecision(BaseModel):
    allowed: bool
    proxy_url_masked: str | None = None
    reason: str | None = None


class BrowserNavigationDecision(BaseModel):
    allowed: bool
    url: str
    reason: str | None = None
    requires_same_origin: bool = False
