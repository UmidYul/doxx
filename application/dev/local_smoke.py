from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import scrapy
import scrapy.http

from config.settings import settings
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_developer_experience_event


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _release_baseline_passing() -> dict[str, object]:
    return {
        "critical_unit_tests_passed": True,
        "contract_tests_passed": True,
        "store_acceptance_passed": True,
        "payload_compatibility_passed": True,
        "lifecycle_replay_safety_passed": True,
        "malformed_response_regression_ok": True,
        "mapping_coverage_regression_ok": True,
        "parse_success_golden_ok": True,
        "compatibility_core_surfaces_clean": True,
        "compatibility_no_unplanned_breaking": True,
        "migration_readiness_acceptable": True,
        "deprecation_removal_safe": True,
        "dual_shape_plan_when_needed": True,
        "cost_perf_regression_gate_ok": True,
        "store_efficiency_policy_ok": True,
        "arch_dependency_gate_ok": True,
        "arch_anti_pattern_gate_ok": True,
        "architecture_lint_report_ok": True,
        "arch_core_import_gate_ok": True,
        "docs_required_present": True,
        "store_playbooks_for_enabled_stores": True,
        "crm_integration_release_support_docs_present": True,
        "docs_coverage_acceptable": True,
        "knowledge_continuity_no_critical_gaps": True,
        "readiness_no_critical_blocking_gaps": True,
        "readiness_required_domains_not_blocked": True,
        "readiness_report_available": True,
        "readiness_enabled_stores_have_evidence": True,
        "readiness_critical_evidence_security_crm_release": True,
    }


class _SmokeRabbitPublisher:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def connect(self) -> None:
        return None

    async def publish(self, event) -> None:
        self.published.append(event)

    async def close(self) -> None:
        return None


async def _run_scraper_db_and_publisher_smoke() -> dict[str, object]:
    from application.ingestion.persistence_service import ScraperPersistenceService
    from infrastructure.persistence.sqlite_store import SQLiteScraperStore
    from infrastructure.spiders.mediapark import MediaparkSpider
    from services.publisher.config import PublisherServiceConfig
    from services.publisher.outbox_reader import SQLiteOutboxReader
    from services.publisher.publication_worker import PublicationWorker

    fixture = _repo_root() / "tests" / "fixtures" / "stores" / "mediapark" / "pdp_phone_reference.html"
    product_url = "https://mediapark.uz/products/view/apple-iphone-15-pro-999001"
    request = scrapy.Request(url=product_url)
    response = scrapy.http.HtmlResponse(
        url=product_url,
        request=request,
        status=200,
        body=fixture.read_bytes(),
        encoding="utf-8",
    )
    spider = MediaparkSpider()
    raw = spider.full_parse_item(response)
    if raw is None:
        return {"pass": False, "reason": "mediapark_fixture_parse_failed"}

    temp_dir = Path(tempfile.mkdtemp(prefix="moscraper-local-smoke-"))
    try:
        db_path = temp_dir / "local-smoke.db"
        store = SQLiteScraperStore(db_path)
        persistence = ScraperPersistenceService(store=store)
        run_id = "local-smoke:mediapark"
        persistence.start_run(
            scrape_run_id=run_id,
            store_name="mediapark",
            spider_name="mediapark",
            category_urls=list(spider.start_category_urls()),
        )
        persisted = persistence.persist_item(
            raw,
            scrape_run_id=run_id,
            event_type=settings.SCRAPER_OUTBOX_EVENT_TYPE,
            exchange_name=settings.RABBITMQ_EXCHANGE,
            routing_key=settings.RABBITMQ_ROUTING_KEY,
        )

        config = PublisherServiceConfig(
            rabbitmq_url=settings.RABBITMQ_URL,
            exchange_name=settings.RABBITMQ_EXCHANGE,
            exchange_type=settings.RABBITMQ_EXCHANGE_TYPE,
            queue_name=settings.RABBITMQ_QUEUE,
            routing_key=settings.RABBITMQ_ROUTING_KEY,
            publish_mandatory=settings.RABBITMQ_PUBLISH_MANDATORY,
            declare_topology=settings.RABBITMQ_DECLARE_TOPOLOGY,
            heartbeat_seconds=settings.RABBITMQ_HEARTBEAT_SECONDS,
            connection_name="local-smoke-publisher",
            batch_size=10,
            lease_seconds=settings.SCRAPER_OUTBOX_LEASE_SECONDS,
            max_retries=settings.SCRAPER_OUTBOX_MAX_RETRIES,
            retry_base_seconds=settings.SCRAPER_OUTBOX_RETRY_BASE_SECONDS,
            poll_interval_seconds=settings.PUBLISHER_POLL_INTERVAL_SECONDS,
            publisher_service_name="local-smoke-publisher",
            scraper_db_path=str(db_path),
        )
        publisher = _SmokeRabbitPublisher()
        worker = PublicationWorker(
            config=config,
            outbox_reader=SQLiteOutboxReader(store=store, config=config),
            rabbit_publisher=publisher,
        )
        try:
            result = await worker.run_once()
        finally:
            await worker.aclose()
            persistence.close()

        outbox_row = store.get_outbox_row(persisted.event_id)
        attempts = store.get_publication_attempts(persisted.outbox_id)
        return {
            "pass": bool(
                result.claimed == 1
                and result.published == 1
                and outbox_row is not None
                and outbox_row.get("status") == "published"
                and len(publisher.published) == 1
                and len(attempts) == 1
            ),
            "claimed": result.claimed,
            "published": result.published,
            "outbox_status": None if outbox_row is None else outbox_row.get("status"),
            "attempts": len(attempts),
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_local_smoke() -> dict[str, object]:
    """Fast layered smoke check for local DX (9B)."""
    from infrastructure.security.startup_guard import reset_startup_security_checks_for_tests

    reset_startup_security_checks_for_tests()

    steps: list[dict[str, Any]] = []
    ok_all = True

    try:
        _ = settings.SCRAPER_DB_PATH
        _ = settings.RABBITMQ_URL
        steps.append({"step": "config_load", "pass": True})
    except Exception as exc:
        ok_all = False
        steps.append({"step": "config_load", "pass": False, "error": str(exc)})

    try:
        from infrastructure.security.startup_guard import run_startup_security_checks

        cfg = settings.model_copy(update={"ENABLE_SECURITY_STARTUP_VALIDATION": False})
        result = run_startup_security_checks(cfg, force=True)
        steps.append(
            {
                "step": "security_startup",
                "pass": bool(result.passed),
                "note": "validation disabled for smoke portability; enable in real runs",
            }
        )
        ok_all = ok_all and result.passed
    except Exception as exc:
        ok_all = False
        steps.append({"step": "security_startup", "pass": False, "error": str(exc)})

    try:
        from application.release.release_gate_evaluator import evaluate_release_gates

        gates = evaluate_release_gates(_release_baseline_passing())
        passed = all(g.passed for g in gates)
        steps.append({"step": "release_gates_baseline", "pass": passed, "gate_count": len(gates)})
        ok_all = ok_all and passed
    except Exception as exc:
        ok_all = False
        steps.append({"step": "release_gates_baseline", "pass": False, "error": str(exc)})

    try:
        from application.qa.run_store_acceptance import run_acceptance_for_store

        report, summary = run_acceptance_for_store("mediapark")
        passed = bool(report.get("quality_gate_passed"))
        steps.append(
            {
                "step": "store_acceptance_fixture",
                "pass": passed,
                "store": "mediapark",
                "summary": summary,
            }
        )
        ok_all = ok_all and passed
    except Exception as exc:
        ok_all = False
        steps.append({"step": "store_acceptance_fixture", "pass": False, "error": str(exc)})

    try:
        smoke = asyncio.run(_run_scraper_db_and_publisher_smoke())
        steps.append({"step": "scraper_db_outbox_publisher", **smoke})
        ok_all = ok_all and bool(smoke.get("pass"))
    except Exception as exc:
        ok_all = False
        steps.append({"step": "scraper_db_outbox_publisher", "pass": False, "error": str(exc)})

    log_developer_experience_event(
        obs_mc.DEV_LOCAL_SMOKE_COMPLETED,
        dev_run_mode=getattr(settings, "DEV_RUN_MODE", "normal"),
        pass_ok=ok_all,
        items_count=len(steps),
        sections_included=[str(step.get("step")) for step in steps],
        details={"steps": steps},
    )
    return {"pass": ok_all, "steps": steps}


def main(argv: list[str] | None = None) -> int:
    """CLI entry for ``python -m application.dev.local_smoke``."""
    result = run_local_smoke()
    print(result)  # noqa: T201
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
