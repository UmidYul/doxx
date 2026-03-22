from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.security.secret_loader import is_secret_configured, load_secret, mask_secret


def test_env_priority_over_file(tmp_path: Path) -> None:
    p = tmp_path / "sec.txt"
    p.write_text("fromfile\n", encoding="utf-8")
    val, desc = load_secret("fromenv", str(p), enable_file_fallback=True)
    assert val == "fromenv"
    assert desc.source == "env"


def test_file_loads_and_trims(tmp_path: Path) -> None:
    p = tmp_path / "k.txt"
    p.write_text("  abc123  \n\n", encoding="utf-8")
    val, desc = load_secret("", str(p), enable_file_fallback=True)
    assert val == "abc123"
    assert desc.source == "file"
    assert desc.configured is True


def test_file_fallback_disabled() -> None:
    val, desc = load_secret("", "/no/such/file", enable_file_fallback=False)
    assert val is None
    assert desc.source == "missing"


def test_masked_preview_safe() -> None:
    assert mask_secret("supersecretvalue") == "su…ue"
    assert mask_secret("ab") == "***"
    assert mask_secret(None) is None


def test_is_secret_configured() -> None:
    assert is_secret_configured(" x ") is True
    assert is_secret_configured("") is False
    assert is_secret_configured(None) is False
