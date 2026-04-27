from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RunRegistry:
    """Small JSON-backed run registry for the operator UI."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"runs": []})

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._read()
            runs = list(payload.get("runs", []))
            return sorted(runs, key=lambda run: str(run.get("started_at") or ""), reverse=True)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            for run in self._read().get("runs", []):
                if run.get("id") == run_id:
                    return deepcopy(run)
        return None

    def upsert(self, run: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            runs = list(payload.get("runs", []))
            run = deepcopy(run)
            run["updated_at"] = utc_now_iso()
            for index, existing in enumerate(runs):
                if existing.get("id") == run.get("id"):
                    runs[index] = run
                    break
            else:
                runs.append(run)
            payload["runs"] = runs
            self._write(payload)
            return deepcopy(run)

    def patch(self, run_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            payload = self._read()
            runs = list(payload.get("runs", []))
            for index, run in enumerate(runs):
                if run.get("id") == run_id:
                    merged = dict(run)
                    merged.update(deepcopy(updates))
                    merged["updated_at"] = utc_now_iso()
                    runs[index] = merged
                    payload["runs"] = runs
                    self._write(payload)
                    return deepcopy(merged)
        return None

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"runs": []}
        except json.JSONDecodeError:
            backup = self.path.with_suffix(".corrupt.json")
            self.path.replace(backup)
            return {"runs": []}

    def _write(self, payload: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.path)

