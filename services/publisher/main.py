from __future__ import annotations

import argparse
import asyncio

from services.publisher.publication_worker import PublicationWorker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish scraper outbox rows to RabbitMQ.")
    parser.add_argument("--once", action="store_true", help="Publish one claimed batch and exit.")
    return parser


async def _run(once: bool) -> None:
    worker = PublicationWorker()
    try:
        if once:
            await worker.run_once()
            return
        await worker.run_forever()
    finally:
        await worker.aclose()


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run(args.once))


if __name__ == "__main__":
    main()
