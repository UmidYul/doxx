from __future__ import annotations

import argparse

from psycopg import connect

from config.settings import settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Requeue scraper publication_outbox rows for replay.")
    parser.add_argument("--dsn", default="", help="Optional DSN override. Defaults to SCRAPER_DB_MIGRATION_DSN or SCRAPER_DB_DSN.")
    parser.add_argument("--event-id", default=None, help="Replay one exact event_id.")
    parser.add_argument("--scrape-run-id", default=None, help="Replay rows from one scrape run.")
    parser.add_argument("--store", default=None, help="Replay rows for one store.")
    parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        default=[],
        help="Optional status filter. Repeatable: --status published --status failed",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of rows to requeue.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    dsn = (args.dsn or settings.SCRAPER_DB_MIGRATION_DSN or settings.SCRAPER_DB_DSN).strip()
    if not dsn:
        raise SystemExit("SCRAPER_DB_MIGRATION_DSN or SCRAPER_DB_DSN must be set for replay")

    statuses = list(args.statuses or [])
    with connect(dsn) as connection:
        row = connection.execute(
            """
            select scraper.requeue_outbox(
                %(event_id)s,
                %(scrape_run_id)s,
                %(store_name)s,
                %(statuses)s,
                %(limit)s
            ) as requeued
            """,
            {
                "event_id": args.event_id,
                "scrape_run_id": args.scrape_run_id,
                "store_name": args.store,
                "statuses": statuses,
                "limit": args.limit,
            },
        ).fetchone()
        connection.commit()

    requeued = 0 if row is None else int(row[0])
    print({"requeued": requeued})  # noqa: T201


if __name__ == "__main__":
    main()
