from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CODE_ROOTS = ("application", "config", "domain", "infrastructure", "tests")
_LEGACY_TASK_FILES = ("celery_app.py", "event_tasks.py", "parse_tasks.py")


def _imports_celery_or_tasks_package(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = (alias.name or "").split(".", 1)[0]
                if base in ("celery", "tasks"):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".", 1)[0]
            if base in ("celery", "tasks"):
                return True
    return False


def test_no_tasks_package_at_repo_root():
    tasks_dir = REPO_ROOT / "tasks"
    assert not tasks_dir.is_dir(), "tasks/ must not exist (no Celery orchestration in-repo)"


def test_pyproject_has_no_celery_or_redis_packages():
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert "celery" not in text
    assert "redis" not in text


def test_no_legacy_celery_task_modules_under_source_trees():
    for name in CODE_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for fname in _LEGACY_TASK_FILES:
            hits = list(root.rglob(fname))
            assert not hits, f"unexpected {fname}: {hits}"


def test_source_trees_do_not_import_celery_or_tasks():
    for name in CODE_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            assert not _imports_celery_or_tasks_package(tree), f"unexpected Celery/tasks import in {path}"
