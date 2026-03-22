"""Thin launcher: ``python scripts/local_smoke.py`` from repo root."""

from __future__ import annotations

import sys

from application.dev.local_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
