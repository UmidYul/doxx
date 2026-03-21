from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MW_DIR = REPO_ROOT / "infrastructure" / "middlewares"

_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "redis",
        "fakeredis",
        "aioredis",
        "pybloom",
        "pybloom_live",
        "probables",
    }
)


def _import_roots(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add((alias.name or "").split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".", 1)[0])
    return out


def test_middleware_files_do_not_import_redis_or_bloom_backends():
    for path in sorted(MW_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = sorted(_import_roots(tree) & _FORBIDDEN_IMPORT_ROOTS)
        assert not bad, f"{path.name}: forbidden imports {bad}"
