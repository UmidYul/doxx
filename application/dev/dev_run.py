from __future__ import annotations

import shlex
import sys

from config.settings import settings
from domain.developer_experience import DevCommandDescriptor, DevRunMode


def explain_dev_run_modes() -> str:
    """Human-readable catalog of dev run modes (9B)."""
    lines = [
        "Dev run modes:",
        "  normal - crawl one store; items persist to scraper DB and outbox.",
        "  dry_run - same crawl command, but keep publication external and leave outbox pending.",
        "  debug - verbose stage output around crawl and persistence.",
        "  fixture_replay - replay legacy normalization fixtures for migration/debug context only.",
        "  acceptance - run fixture-based acceptance for the active ingestion flow.",
    ]
    return "\n".join(lines)


def resolve_single_store_target(
    store_name: str,
    *,
    store_names: list[str] | None = None,
) -> dict[str, object]:
    """Validate a store against configured STORE_NAMES and return concrete run hints."""
    allowed = list(store_names or settings.STORE_NAMES)
    spider = store_name.strip()
    ok = spider in allowed
    return {
        "ok": ok,
        "store_name": spider,
        "allowed_stores": allowed,
        "scrapy_argv": [sys.executable, "-m", "scrapy", "crawl", spider],
        "env_hints": {
            "DEV_MODE": "true",
            "DEV_RUN_MODE": "normal",
            "TRANSPORT_TYPE": "disabled",
            "SCRAPER_DB_BACKEND": "sqlite",
            "SCRAPER_DB_PATH": f"data/scraper/{spider or 'store'}.dev.db",
        },
        "notes": (
            []
            if ok
            else [f"Store {spider!r} not in STORE_NAMES; check config/settings or .env"]
        )
        + ["Run `python -m services.publisher.main --once` separately if you want Rabbit publication."],
    }


def build_dev_run_command(
    mode: DevRunMode | str,
    *,
    store_name: str | None = None,
    spider_name: str | None = None,
    fixture_path: str | None = None,
    extra_scrapy_args: list[str] | None = None,
) -> list[str]:
    """Build an argv list for local subprocess use (repo root as cwd)."""
    spider = (spider_name or store_name or "").strip()
    extras = list(extra_scrapy_args or [])
    base = [sys.executable, "-m", "scrapy", "crawl", spider] if spider else [sys.executable, "-m", "scrapy", "list"]

    if mode == "fixture_replay" and fixture_path:
        return [
            sys.executable,
            "-c",
            "from application.dev.fixture_replay import replay_normalization_fixture; "
            "import json,sys; print(json.dumps(replay_normalization_fixture(sys.argv[1]), default=str))",
            fixture_path,
        ]

    if mode == "acceptance":
        return [sys.executable, "-m", "pytest", "tests/acceptance", "-q"] + extras

    if mode in ("dry_run", "debug"):
        return base + extras

    return base + extras


def describe_commands() -> list[DevCommandDescriptor]:
    """Structured catalog for tooling / docs."""
    return [
        DevCommandDescriptor(
            name="single_store_crawl",
            purpose="Run one spider and persist raw items into scraper DB/outbox",
            example=shlex.join(build_dev_run_command("normal", store_name="mediapark")),
            notes=["Limit items: add `-s CLOSESPIDER_ITEMCOUNT=5` after crawl args"],
        ),
        DevCommandDescriptor(
            name="publisher_once",
            purpose="Publish one outbox batch to RabbitMQ",
            example=shlex.join([sys.executable, "-m", "services.publisher.main", "--once"]),
            notes=["Run after a crawl if you want to flush pending outbox rows"],
        ),
        DevCommandDescriptor(
            name="fixture_normalization",
            purpose="Replay a legacy normalization JSON fixture for migration/debug only",
            example=shlex.join(
                build_dev_run_command("fixture_replay", fixture_path="tests/fixtures/regression/normalization/laptop.json")
            ),
            notes=["Not part of the active scraper runtime"],
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m application.dev.dev_run modes|resolve <store>|command ...``"""
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help", "help"):
        print(explain_dev_run_modes())
        return 0
    if args[0] == "modes":
        print(explain_dev_run_modes())
        return 0
    if args[0] == "resolve" and len(args) > 1:
        result = resolve_single_store_target(args[1])
        print(result)
        return 0 if result.get("ok") else 1
    if args[0] == "command":
        mode = args[1] if len(args) > 1 else "normal"
        print(shlex.join(build_dev_run_command(mode, store_name=args[2] if len(args) > 2 else None)))  # noqa: T201
        return 0
    print("Usage: dev_run [modes|resolve <store>|command <mode> [store]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
