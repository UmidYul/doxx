from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import settings
from services.ui_api.run_registry import RunRegistry, utc_now_iso


SUMMARY_RE = re.compile(
    r"scrape_run_summary run_id=(?P<scrape_run_id>\S+) store=(?P<store>\S+) status=(?P<status>\S+) "
    r"scraped_items=(?P<scraped>\S+) persisted_items=(?P<persisted>\S+) failed_pdp=(?P<failed>\S+) "
    r"pages_visited=(?P<pages>\S+) spec_coverage_ratio=(?P<spec>\S+) image_coverage_ratio=(?P<image>\S+)"
)
SPIDER_CLOSED_RE = re.compile(r"Spider closed \((?P<reason>[^)]+)\)")
SCRAPER_DB_SAVED_RE = re.compile(r"scraper_db_saved .* raw_product_id=(?P<raw_product_id>\d+)")
LISTING_PAGE_RE = re.compile(r'"event": "LISTING_PAGE"')
SCRAPE_RUN_ID_RE = re.compile(r'"run_id": "(?P<scrape_run_id>[a-zA-Z0-9_-]+:[^"]+)"')


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _safe_ratio_percent(value: object) -> int | None:
    ratio = _to_float(value)
    if ratio is None:
        return None
    return round(ratio * 100)


@dataclass(slots=True)
class StartRunRequest:
    store: str
    time_limit_minutes: int | None = None
    item_limit: int | None = None
    parse_interval_seconds: float | None = None
    category: str | None = None
    brand: str | None = None
    category_url: str | None = None
    run_until_stopped: bool = False


class ScraperRunner:
    """Launches Scrapy as a subprocess and keeps UI-facing process state."""

    def __init__(self, *, registry: RunRegistry, repo_root: str | Path) -> None:
        self.registry = registry
        self.repo_root = Path(repo_root)
        self.logs_dir = self.repo_root / "data" / "ui" / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.repo_root / "data" / "scraper" / "ui_runs.db"
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._stop_requested: set[str] = set()

    def start(self, request: StartRunRequest) -> dict[str, Any]:
        stores = set(settings.STORE_NAMES)
        if request.store not in stores:
            raise ValueError(f"Unknown store: {request.store}")
        if not request.run_until_stopped:
            if request.time_limit_minutes is not None and request.time_limit_minutes <= 0:
                raise ValueError("time_limit_minutes must be greater than zero")
            if request.item_limit is not None and request.item_limit <= 0:
                raise ValueError("item_limit must be greater than zero")
            if request.time_limit_minutes is None and request.item_limit is None:
                raise ValueError("Set a time limit, item limit, or enable Run until stopped")
        if request.parse_interval_seconds is not None and request.parse_interval_seconds <= 0:
            raise ValueError("parse_interval_seconds must be greater than zero")
        if request.run_until_stopped:
            request.time_limit_minutes = None
            request.item_limit = None

        run_id = f"ui-{request.store}-{_utc_timestamp()}-{uuid.uuid4().hex[:8]}"
        log_path = self.logs_dir / f"{run_id}.log"
        command = self._build_command(request)
        env = self._build_env()
        started_at = utc_now_iso()
        run = {
            "id": run_id,
            "status": "starting",
            "store": request.store,
            "started_at": started_at,
            "finished_at": None,
            "duration_seconds": 0,
            "items_scraped": 0,
            "items_persisted": 0,
            "pages_visited": 0,
            "errors": 0,
            "warnings": 0,
            "stop_reason": None,
            "time_limit_minutes": request.time_limit_minutes,
            "item_limit": request.item_limit,
            "parse_interval_seconds": request.parse_interval_seconds,
            "category": request.category,
            "brand": request.brand,
            "category_url": request.category_url,
            "run_until_stopped": request.run_until_stopped,
            "command": command,
            "log_path": str(log_path),
            "scraper_db_path": str(self.db_path),
            "summary": {},
            "created_at": started_at,
            "updated_at": started_at,
        }
        self.registry.upsert(run)

        log_file = log_path.open("w", encoding="utf-8", buffering=1)
        log_file.write(f"UI_RUN_START run_id={run_id} store={request.store}\n")
        process = subprocess.Popen(
            command,
            cwd=str(self.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        with self._lock:
            self._processes[run_id] = process
        self.registry.patch(run_id, {"status": "running", "pid": process.pid})
        thread = threading.Thread(
            target=self._watch_process,
            args=(run_id, process, log_file),
            name=f"moscraper-ui-run-{run_id}",
            daemon=True,
        )
        thread.start()
        return self.registry.get(run_id) or run

    def stop(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(run_id)
            self._stop_requested.add(run_id)
        if process is None:
            run = self.registry.get(run_id)
            if run is None:
                raise KeyError(run_id)
            return run
        self.registry.patch(run_id, {"status": "stopping", "stop_reason": "manual stop requested"})
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        return self.registry.get(run_id) or {}

    def refresh_active(self) -> None:
        with self._lock:
            active = list(self._processes.items())
        for run_id, process in active:
            run = self.registry.get(run_id)
            if run is None:
                continue
            started_at = _parse_iso(run.get("started_at"))
            duration = max(0, int((datetime.now(UTC) - started_at).total_seconds())) if started_at else 0
            self.registry.patch(run_id, {"duration_seconds": duration})
            if process.poll() is not None:
                with self._lock:
                    self._processes.pop(run_id, None)

    def _build_command(self, request: StartRunRequest) -> list[str]:
        command = [sys.executable, "-m", "scrapy", "crawl", request.store]
        if request.time_limit_minutes is not None:
            command.extend(["-s", f"CLOSESPIDER_TIMEOUT={request.time_limit_minutes * 60}"])
        if request.item_limit is not None:
            command.extend(["-s", f"CLOSESPIDER_ITEMCOUNT={request.item_limit}"])
        if request.parse_interval_seconds is not None:
            command.extend(["-s", f"DOWNLOAD_DELAY={request.parse_interval_seconds:g}"])
        if request.category:
            command.extend(["-a", f"category={request.category}"])
        if request.brand:
            command.extend(["-a", f"brand={request.brand}"])
        if request.category_url:
            command.extend(["-a", f"category_url={request.category_url}"])
        return command

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "DEV_MODE": "true",
                "DEV_RUN_MODE": "normal",
                "TRANSPORT_TYPE": "disabled",
                "SCRAPER_DB_BACKEND": "sqlite",
                "SCRAPER_DB_PATH": str(self.db_path),
                "SCRAPY_LOG_LEVEL": env.get("SCRAPY_LOG_LEVEL", "INFO"),
            }
        )
        return env

    def _watch_process(self, run_id: str, process: subprocess.Popen[str], log_file) -> None:
        summary: dict[str, Any] = {}
        live_items = 0
        live_pages = 0
        seen_raw_product_ids: set[str] = set()
        warnings = 0
        errors = 0
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip("\n")
                log_file.write(line + "\n")
                if " WARNING:" in line or " WARN " in line:
                    warnings += 1
                if " ERROR:" in line or " ERROR " in line:
                    errors += 1
                progress = parse_live_progress_line(line)
                if progress.get("raw_product_id"):
                    raw_product_id = str(progress["raw_product_id"])
                    if raw_product_id not in seen_raw_product_ids:
                        seen_raw_product_ids.add(raw_product_id)
                        live_items += 1
                        summary["items_scraped"] = live_items
                        summary["items_persisted"] = live_items
                        self.registry.patch(
                            run_id,
                            {
                                "items_scraped": live_items,
                                "items_persisted": live_items,
                                "summary": dict(summary, items_scraped=live_items, items_persisted=live_items),
                            },
                        )
                if progress.get("scrape_run_id"):
                    summary["scrape_run_id"] = progress["scrape_run_id"]
                    self.registry.patch(run_id, {"scrape_run_id": progress["scrape_run_id"], "summary": summary})
                if progress.get("listing_page"):
                    live_pages += 1
                    self.registry.patch(run_id, {"pages_visited": live_pages})
                parsed = parse_summary_line(line)
                if parsed:
                    summary.update(parsed)
                    self.registry.patch(
                        run_id,
                        {
                            "scrape_run_id": parsed.get("scrape_run_id"),
                            "items_scraped": parsed.get("items_scraped", 0),
                            "items_persisted": parsed.get("items_persisted", 0),
                            "pages_visited": parsed.get("pages_visited", 0),
                            "summary": summary,
                        },
                    )
                reason = parse_finish_reason(line)
                if reason:
                    summary["finish_reason"] = reason
        finally:
            exit_code = process.wait()
            finished_at = utc_now_iso()
            run = self.registry.get(run_id) or {}
            started_at = _parse_iso(run.get("started_at"))
            duration = max(0, int((datetime.now(UTC) - started_at).total_seconds())) if started_at else 0
            stopped = run_id in self._stop_requested
            status = "stopped" if stopped else ("completed" if exit_code == 0 else "failed")
            stop_reason = summary.get("finish_reason")
            if stopped:
                stop_reason = "manual stop"
            elif not stop_reason:
                stop_reason = "finished" if exit_code == 0 else f"exit code {exit_code}"
            log_file.write(f"UI_RUN_FINISH run_id={run_id} status={status} exit_code={exit_code}\n")
            log_file.close()
            final_summary = dict(summary)
            if live_items and "items_scraped" not in final_summary:
                final_summary["items_scraped"] = live_items
                final_summary["items_persisted"] = live_items
            if live_pages and "pages_visited" not in final_summary:
                final_summary["pages_visited"] = live_pages
            self.registry.patch(
                run_id,
                {
                    "status": status,
                    "exit_code": exit_code,
                    "finished_at": finished_at,
                    "duration_seconds": duration,
                    "errors": errors,
                    "warnings": warnings,
                    "stop_reason": stop_reason,
                    "items_scraped": int(final_summary.get("items_scraped") or run.get("items_scraped") or 0),
                    "items_persisted": int(final_summary.get("items_persisted") or run.get("items_persisted") or 0),
                    "pages_visited": int(final_summary.get("pages_visited") or run.get("pages_visited") or 0),
                    "summary": final_summary,
                },
            )
            with self._lock:
                self._processes.pop(run_id, None)
                self._stop_requested.discard(run_id)


def parse_summary_line(line: str) -> dict[str, Any] | None:
    match = SUMMARY_RE.search(line)
    if not match:
        return None
    data = match.groupdict()
    return {
        "scrape_run_id": data["scrape_run_id"],
        "store": data["store"],
        "pipeline_status": data["status"],
        "items_scraped": _to_int(data["scraped"]),
        "items_persisted": _to_int(data["persisted"]),
        "failed_pdp": _to_int(data["failed"]),
        "pages_visited": _to_int(data["pages"]),
        "spec_coverage_percent": _safe_ratio_percent(data["spec"]),
        "image_coverage_percent": _safe_ratio_percent(data["image"]),
    }


def parse_live_progress_line(line: str) -> dict[str, object]:
    progress: dict[str, object] = {}
    saved_match = SCRAPER_DB_SAVED_RE.search(line)
    if saved_match:
        progress["raw_product_id"] = saved_match.group("raw_product_id")
    run_match = SCRAPE_RUN_ID_RE.search(line)
    if run_match:
        progress["scrape_run_id"] = run_match.group("scrape_run_id")
    if LISTING_PAGE_RE.search(line):
        progress["listing_page"] = True
    return progress


def parse_finish_reason(line: str) -> str | None:
    match = SPIDER_CLOSED_RE.search(line)
    if not match:
        return None
    return match.group("reason")


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if sys.platform != "win32":
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    else:
        process.terminate()
