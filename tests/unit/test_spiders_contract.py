from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIDERS_DIR = REPO_ROOT / "infrastructure" / "spiders"

# Spiders must not open DB sessions or call CRM HTTP from crawl code.
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "sqlalchemy",
        "supabase",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "aiosqlite",
        "sqlite3",
        "pymongo",
        "motor",
        "peewee",
        "django",
        "celery",
    }
)


def _collect_import_roots(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add((alias.name or "").split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".", 1)[0])
    return out


def test_spider_modules_do_not_import_database_clients():
    for path in sorted(SPIDERS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots = _collect_import_roots(tree)
        bad = sorted(roots & _FORBIDDEN_IMPORT_ROOTS)
        assert not bad, f"{path.name} must not import {bad}"
