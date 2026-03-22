from __future__ import annotations

import shlex
import sys

from domain.developer_experience import DevCommandDescriptor, DevRunMode

from config.settings import settings


def explain_dev_run_modes() -> str:
    """Human-readable catalog of dev run modes (9B)."""
    lines = [
        "Dev run modes:",
        "  normal — default crawl; use DEV_MODE=true + env from resolve_single_store_target for dry CRM.",
        "  dry_run — same as normal but CRM HTTP suppressed via DryRunTransport (DEV_MODE + DEV_DRY_RUN_DISABLE_CRM_SEND).",
        "  debug — verbose stage output (DEV_ENABLE_VERBOSE_STAGE_OUTPUT=true) + DEV_MODE.",
        "  fixture_replay — run application.dev.fixture_replay helpers on JSON fixtures (no CRM).",
        "  acceptance — short crawl / contract checks; see DEV_WORKFLOW.md.",
    ]
    return "\n".join(lines)


def resolve_single_store_target(
    store_name: str,
    *,
    store_names: list[str] | None = None,
) -> dict[str, object]:
    """Validate a store against configured STORE_NAMES and return concrete run hints."""
    allowed = list(store_names or settings.STORE_NAMES)
    ok = store_name.strip() in allowed
    spider = store_name.strip()
    return {
        "ok": ok,
        "store_name": spider,
        "allowed_stores": allowed,
        "scrapy_argv": [sys.executable, "-m", "scrapy", "crawl", spider],
        "env_hints": {
            "DEV_MODE": "true",
            "DEV_RUN_MODE": "normal",
            "DEV_DRY_RUN_DISABLE_CRM_SEND": "true",
            "TRANSPORT_TYPE": "crm_http",
        },
        "notes": [] if ok else [f"Store {spider!r} not in STORE_NAMES; check config/settings or .env"],
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

    if mode in ("fixture_replay",) and fixture_path:
        return [
            sys.executable,
            "-c",
            "from application.dev.fixture_replay import replay_normalization_fixture; "
            "import json,sys; print(json.dumps(replay_normalization_fixture(sys.argv[1]), default=str))",
            fixture_path,
        ]

    if mode == "acceptance":
        return [sys.executable, "-m", "pytest", "tests/contracts", "-q", "--tb=no"] + extras

    if mode == "dry_run":
        # Caller should set DEV_MODE=1 in environment; command stays a normal crawl.
        return base + extras

    if mode == "debug":
        return base + extras

    return base + extras


def describe_commands() -> list[DevCommandDescriptor]:
    """Structured catalog for tooling / docs."""
    return [
        DevCommandDescriptor(
            name="single_store_crawl",
            purpose="Run one spider matching a store",
            example=shlex.join(build_dev_run_command("normal", store_name="mediapark")),
            notes=["Limit items: add `-s CLOSESPIDER_ITEMCOUNT=5` after crawl args"],
        ),
        DevCommandDescriptor(
            name="dry_run_crawl",
            purpose="Crawl with CRM dry-run transport",
            example="set DEV_MODE=true then " + shlex.join(build_dev_run_command("dry_run", store_name="mediapark")),
            notes=["Requires TRANSPORT_TYPE=crm_http", "Do not set MOSCRAPER_DISABLE_PUBLISH unless you want fully disabled transport"],
        ),
        DevCommandDescriptor(
            name="fixture_normalization",
            purpose="Replay a normalization JSON fixture",
            example=shlex.join(
                build_dev_run_command("fixture_replay", fixture_path="tests/fixtures/regression/normalization/laptop.json")
            ),
            notes=[],
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
        r = resolve_single_store_target(args[1])
        print(r)
        return 0 if r.get("ok") else 1
    if args[0] == "command":
        mode = args[1] if len(args) > 1 else "normal"
        print(shlex.join(build_dev_run_command(mode, store_name=args[2] if len(args) > 2 else None)))  # noqa: T201
        return 0
    print("Usage: dev_run [modes|resolve <store>|command <mode> [store]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
