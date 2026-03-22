"""Thin launcher: ``python scripts/dev_run.py`` from repo root."""

from __future__ import annotations

import sys

from application.dev.dev_run import main

if __name__ == "__main__":
    raise SystemExit(main())
