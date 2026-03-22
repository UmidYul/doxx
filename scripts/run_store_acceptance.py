"""CLI shim: ``python scripts/run_store_acceptance.py`` → :mod:`application.qa.run_store_acceptance`."""

from __future__ import annotations

from application.qa.run_store_acceptance import main

if __name__ == "__main__":
    raise SystemExit(main())
