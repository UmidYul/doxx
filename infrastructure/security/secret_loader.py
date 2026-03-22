from __future__ import annotations

import re
from pathlib import Path

from domain.security import SecretDescriptor, SecretSource


def is_secret_configured(value: str | None) -> bool:
    if value is None or not isinstance(value, str):
        return False
    return bool(value.strip())


def mask_secret(value: str | None, keep_start: int = 2, keep_end: int = 2) -> str | None:
    """Non-reversible preview; never suitable for auth."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) <= keep_start + keep_end:
        return "***"
    return f"{s[:keep_start]}…{s[-keep_end:]}"


def load_secret(
    value: str | None,
    file_path: str | None = None,
    *,
    name: str = "secret",
    enable_file_fallback: bool = True,
) -> tuple[str | None, SecretDescriptor]:
    """
    Resolve secret: env ``value`` first, then optional file.
    Trims whitespace/newlines. Never logs raw value here.
    """
    env_raw = ((value if isinstance(value, str) else "") or "").strip()
    if env_raw:
        return env_raw, SecretDescriptor(
            name=name,
            source="env",
            configured=True,
            masked_preview=mask_secret(env_raw),
        )

    if not enable_file_fallback:
        return None, SecretDescriptor(
            name=name,
            source="missing",
            configured=False,
            masked_preview=None,
        )

    fp = (file_path or "").strip()
    if not fp:
        return None, SecretDescriptor(
            name=name,
            source="missing",
            configured=False,
            masked_preview=None,
        )

    try:
        raw = Path(fp).read_text(encoding="utf-8")
    except OSError:
        return None, SecretDescriptor(
            name=name,
            source="file",
            configured=False,
            masked_preview=None,
        )

    secret = raw.strip()
    if not secret:
        return None, SecretDescriptor(
            name=name,
            source="file",
            configured=False,
            masked_preview=None,
        )

    return secret, SecretDescriptor(
        name=name,
        source="file",
        configured=True,
        masked_preview=mask_secret(secret),
    )


_WS_RE = re.compile(r"\s+")


def normalize_header_name(name: str) -> str:
    return _WS_RE.sub(" ", (name or "").strip())
