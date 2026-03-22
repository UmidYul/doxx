"""Run production readiness assessment: ``python scripts/check_readiness.py [project_root]``."""

from __future__ import annotations

import sys

from application.readiness.check_readiness import main

if __name__ == "__main__":
    raise SystemExit(main())
