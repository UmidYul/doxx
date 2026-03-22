from __future__ import annotations

import json
from pathlib import Path


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def list_available_store_fixtures(store_name: str | None = None) -> list[str]:
    """Return relative paths (posix) under ``tests/fixtures`` for discoverability."""
    root = _fixtures_root()
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*.json")):
        rel = p.relative_to(root.parent).as_posix()
        if store_name:
            s = store_name.strip().lower()
            if s not in p.as_posix().lower():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    src = ""
                    if isinstance(data, dict):
                        raw = data.get("raw_item")
                        if isinstance(raw, dict):
                            src = str(raw.get("source") or "").lower()
                        norm = data.get("normalized")
                        if isinstance(norm, dict):
                            src = src or str(norm.get("store") or "").lower()
                    if s not in src and s not in rel.lower():
                        continue
                except OSError:
                    continue
        out.append(rel)
    return out


def load_fixture_text(path: str) -> str:
    p = Path(path)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    base_fix = _fixtures_root()
    if (base_fix / path).is_file():
        return (base_fix / path).read_text(encoding="utf-8")
    tests_dir = Path(__file__).resolve().parents[1]
    if (tests_dir / path).is_file():
        return (tests_dir / path).read_text(encoding="utf-8")
    raise FileNotFoundError(path)


def load_fixture_json(path: str) -> dict:
    raw = load_fixture_text(path)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Fixture JSON must be an object at the root")
    return data


def build_fixture_summary(path: str) -> dict[str, object]:
    """Compact metadata for picking a sample fixture."""
    txt = load_fixture_text(path)
    data = json.loads(txt)
    keys = list(data.keys()) if isinstance(data, dict) else []
    store_hint: str | None = None
    if isinstance(data, dict):
        ri = data.get("raw_item")
        if isinstance(ri, dict):
            store_hint = str(ri.get("source") or "") or None
        norm = data.get("normalized")
        if isinstance(norm, dict) and not store_hint:
            store_hint = str(norm.get("store") or "") or None
    return {
        "path": path,
        "size_bytes": len(txt.encode("utf-8")),
        "top_level_keys": keys[:24],
        "store_hint": store_hint,
        "kind": "regression" if "regression" in path.replace("\\", "/") else "unknown",
    }
