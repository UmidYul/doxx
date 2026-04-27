from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CODE_ROOTS = ("application", "config", "domain", "infrastructure")

_PYPROJECT_FORBIDDEN = (
    "supabase",
    "asyncpg",
    "sqlalchemy",
    "alembic",
)

_SOURCE_FORBIDDEN_SUBSTRINGS = (
    "get_supabase",
    "from supabase",
    "import supabase",
    "infrastructure.db",
)


def test_infrastructure_db_directory_absent():
    db_dir = REPO_ROOT / "infrastructure" / "db"
    assert not db_dir.exists()


def test_pyproject_excludes_database_client_dependencies():
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    for needle in _PYPROJECT_FORBIDDEN:
        assert needle not in text, f"pyproject must not reference {needle!r}"


def test_source_trees_exclude_supabase_and_db_package_refs():
    lowered = tuple(s.lower() for s in _SOURCE_FORBIDDEN_SUBSTRINGS)
    for name in CODE_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            low = path.read_text(encoding="utf-8").lower()
            for sub in lowered:
                assert sub not in low, f"{path}: must not contain {sub!r}"
