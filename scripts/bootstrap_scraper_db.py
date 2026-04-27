from __future__ import annotations

import argparse

from config.settings import settings
from infrastructure.persistence.postgres_store import apply_postgres_schema


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply scraper Postgres schema/bootstrap SQL.")
    parser.add_argument(
        "--dsn",
        default="",
        help="Optional DSN override. Defaults to SCRAPER_DB_MIGRATION_DSN or SCRAPER_DB_DSN.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    dsn = (args.dsn or settings.SCRAPER_DB_MIGRATION_DSN or settings.SCRAPER_DB_DSN).strip()
    if not dsn:
        raise SystemExit("SCRAPER_DB_MIGRATION_DSN or SCRAPER_DB_DSN must be set for bootstrap")
    apply_postgres_schema(dsn)


if __name__ == "__main__":
    main()
