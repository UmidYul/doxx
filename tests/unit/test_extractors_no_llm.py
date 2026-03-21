from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTORS = REPO_ROOT / "application" / "extractors"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_extractors_dir_has_no_llm_or_spec_extractor_modules():
    py_files = {p.name for p in EXTRACTORS.glob("*.py")}
    assert "llm_extractor.py" not in py_files
    assert "spec_extractor.py" not in py_files


@pytest.mark.parametrize(
    "forbidden",
    ["anthropic", "openai", "redis"],
)
def test_pyproject_has_no_llm_or_redis_client_deps(forbidden: str):
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert forbidden not in text
