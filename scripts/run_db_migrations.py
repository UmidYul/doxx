#!/usr/bin/env python3
"""Run Alembic upgrade head, then apply 002_supabase_functions (increment_retry).

Usage (from repo root):
  python scripts/run_db_migrations.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
    )
    if r.returncode != 0:
        return r.returncode
    r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "apply_supabase_functions.py")], cwd=ROOT, env=env)
    return r2.returncode


if __name__ == "__main__":
    raise SystemExit(main())
