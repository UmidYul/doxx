from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOTS = ("application", "infrastructure")

_FORBIDDEN = frozenset(
    {
        "celery",
        "apscheduler",
        "django_celery_beat",
        "schedule",  # pip "schedule" library (often used for in-process cron)
    }
)


def _import_roots(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = (alias.name or "").split(".", 1)[0].lower()
                out.add(base)
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".", 1)[0].lower()
            out.add(base)
    return out


def test_no_tasks_directory_for_periodic_jobs():
    assert not (REPO_ROOT / "tasks").is_dir()


def test_application_and_infrastructure_avoid_scheduler_libraries():
    for name in ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            bad = sorted(_import_roots(tree) & _FORBIDDEN)
            assert not bad, f"{path}: in-process scheduler stacks forbidden: {bad}"
