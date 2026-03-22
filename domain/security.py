from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SecurityMode = Literal["baseline", "hardened"]
SecretSource = Literal["env", "file", "inline", "missing"]
RequestIntegrityMode = Literal["none", "hmac_optional", "hmac_required"]


class SecurityValidationResult(BaseModel):
    passed: bool
    mode: SecurityMode
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SecretDescriptor(BaseModel):
    name: str
    source: SecretSource
    configured: bool
    masked_preview: str | None = None


class RequestSecurityContext(BaseModel):
    parser_key_present: bool
    integrity_mode: RequestIntegrityMode
    timestamp_header: str | None = None
    nonce_header: str | None = None
    signature_header: str | None = None
