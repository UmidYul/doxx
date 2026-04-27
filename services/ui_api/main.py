from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sqlite3
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlsplit

from config.settings import settings
from services.ui_api.run_registry import RunRegistry
from services.ui_api.scraper_runner import SCRAPE_RUN_ID_RE, ScraperRunner, StartRunRequest
from services.publisher.config import PublisherServiceConfig
from services.publisher.publication_worker import PublicationWorker

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
REGISTRY_PATH = REPO_ROOT / "data" / "ui" / "runs.json"

registry = RunRegistry(REGISTRY_PATH)
runner = ScraperRunner(registry=registry, repo_root=REPO_ROOT)


class UIRequestHandler(BaseHTTPRequestHandler):
    server_version = "MoscraperUI/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health" or path == "/api/diagnostics":
            self._json(diagnostics_payload())
            return
        if path == "/api/stores":
            self._json({"stores": list(settings.STORE_NAMES)})
            return
        if path == "/api/runs":
            runner.refresh_active()
            self._json({"runs": list_runs_payload()})
            return
        if path == "/api/publication/status":
            self._json(publication_status_payload(parse_qs(parsed.query)))
            return
        if path.startswith("/api/runs/"):
            self._handle_run_get(path, parse_qs(parsed.query))
            return
        if path.startswith("/api/"):
            self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/runs":
            self._handle_run_start()
            return
        if path == "/api/publication/publish-once":
            self._handle_publish_once()
            return
        if path.startswith("/api/runs/") and path.endswith("/stop"):
            run_id = path.removeprefix("/api/runs/").removesuffix("/stop").strip("/")
            try:
                self._json(runner.stop(run_id))
            except KeyError:
                self._json({"error": "run not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("ui_api " + format % args + "\n")

    def _handle_run_start(self) -> None:
        try:
            payload = self._read_json()
            request = StartRunRequest(
                store=str(payload.get("store", "")).strip(),
                time_limit_minutes=_optional_positive_int(payload.get("time_limit_minutes")),
                item_limit=_optional_positive_int(payload.get("item_limit")),
                parse_interval_seconds=_optional_positive_float(payload.get("parse_interval_seconds")),
                category=_optional_text(payload.get("category")),
                brand=_optional_text(payload.get("brand")),
                category_url=_optional_text(payload.get("category_url")),
                run_until_stopped=bool(payload.get("run_until_stopped")),
            )
            run = runner.start(request)
            self._json(run, status=HTTPStatus.CREATED)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_publish_once(self) -> None:
        try:
            payload = self._read_json()
            run_id = str(payload.get("run_id") or "").strip() or None
            result = publish_once()
            self._json(
                {
                    "result": result,
                    "status": publication_status(run_id=run_id),
                    "all_status": publication_status(run_id=None),
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)

    def _handle_run_get(self, path: str, query: dict[str, list[str]]) -> None:
        rest = path.removeprefix("/api/runs/").strip("/")
        if rest.endswith("/logs"):
            run_id = rest.removesuffix("/logs").strip("/")
            self._json(read_log_payload(run_id, query))
            return
        if rest.endswith("/summary"):
            run_id = rest.removesuffix("/summary").strip("/")
            run = registry.get(run_id)
            if run is None:
                self._json({"error": "run not found"}, status=HTTPStatus.NOT_FOUND)
            else:
                self._json({"summary": run.get("summary") or {}, "run": enrich_run(run)})
            return
        run = registry.get(rest)
        if run is None:
            self._json({"error": "run not found"}, status=HTTPStatus.NOT_FOUND)
        else:
            self._json(enrich_run(run))

    def _serve_static(self, path: str) -> None:
        target = STATIC_DIR / "index.html" if path in ("", "/") else STATIC_DIR / path.lstrip("/")
        try:
            resolved = target.resolve()
            if not str(resolved).startswith(str(STATIC_DIR.resolve())):
                raise FileNotFoundError
            if not resolved.exists() or resolved.is_dir():
                resolved = STATIC_DIR / "index.html"
            content = resolved.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload: object, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def read_log_payload(run_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    run = registry.get(run_id)
    if run is None:
        return {"error": "run not found", "lines": [], "next_offset": 0}
    log_path = Path(str(run.get("log_path") or ""))
    offset = _optional_nonnegative_int(_first(query, "offset")) or 0
    severity = (_first(query, "level") or "ALL").upper()
    search = (_first(query, "q") or "").lower()
    if not log_path.exists():
        return {"lines": [], "next_offset": 0, "run": run}
    with log_path.open("rb") as file:
        file.seek(max(0, offset))
        data = file.read(256_000)
        next_offset = file.tell()
    text = data.decode("utf-8", errors="replace")
    include_internal = (_first(query, "internal") or "").lower() in ("1", "true", "yes")
    lines = [
        format_log_line(line)
        for line in text.splitlines()
        if line.strip() and (include_internal or not is_internal_noise(line))
    ]
    if severity != "ALL":
        lines = [line for line in lines if line["level"] == severity]
    if search:
        lines = [line for line in lines if search in line["message"].lower()]
    return {"lines": lines, "next_offset": next_offset, "run": run}


def publication_status_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    run_id = _first(query, "run_id")
    return {"status": publication_status(run_id=run_id), "all_status": publication_status(run_id=None)}


def list_runs_payload() -> list[dict[str, Any]]:
    return [enrich_run(run) for run in registry.list_runs()]


def enrich_run(run: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(run)
    run_id = str(enriched.get("id") or "")
    publication = publication_status(run_id=run_id) if run_id else {}
    enriched["publication_status"] = publication
    if publication.get("scrape_run_id") and not enriched.get("scrape_run_id"):
        enriched["scrape_run_id"] = publication["scrape_run_id"]
    enriched["display_status"] = "published" if publication_is_complete(publication) else str(
        enriched.get("status") or "unknown"
    )
    return enriched


def publication_is_complete(status: dict[str, Any]) -> bool:
    total = int(status.get("total") or 0)
    if total <= 0:
        return False
    return (
        int(status.get("published") or 0) == total
        and int(status.get("pending") or 0) == 0
        and int(status.get("retryable") or 0) == 0
        and int(status.get("failed") or 0) == 0
        and int(status.get("other") or 0) == 0
    )


def publication_status(*, run_id: str | None) -> dict[str, Any]:
    run = registry.get(run_id) if run_id else None
    scrape_run_id = resolve_scrape_run_id_for_run(run) if run else ""
    status: dict[str, Any] = {
        "run_id": run_id,
        "scrape_run_id": scrape_run_id or None,
        "total": 0,
        "pending": 0,
        "published": 0,
        "retryable": 0,
        "failed": 0,
        "other": 0,
    }
    db_path = runner.db_path
    if not db_path.exists():
        return status
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(db_path))
        cursor = connection.cursor()
        if scrape_run_id:
            rows = cursor.execute(
                "select status, count(*) from publication_outbox where scrape_run_id = ? group by status",
                (scrape_run_id,),
            ).fetchall()
        elif run_id:
            rows = []
        else:
            rows = cursor.execute("select status, count(*) from publication_outbox group by status").fetchall()
    except sqlite3.Error as exc:
        status["error"] = str(exc)
        return status
    finally:
        if connection is not None:
            connection.close()
    for row_status, count in rows:
        key = str(row_status or "other")
        amount = int(count)
        status["total"] += amount
        if key in status:
            status[key] += amount
        else:
            status["other"] += amount
    return status


def resolve_scrape_run_id_for_run(run: dict[str, Any] | None) -> str:
    if not run:
        return ""
    existing = str(run.get("scrape_run_id") or (run.get("summary") or {}).get("scrape_run_id") or "")
    if existing:
        return existing

    from_log = scrape_run_id_from_log(Path(str(run.get("log_path") or "")), store_name=str(run.get("store") or ""))
    if from_log:
        patch_run_scrape_id(run, from_log)
        return from_log

    from_db = scrape_run_id_from_db(run)
    if from_db:
        patch_run_scrape_id(run, from_db)
        return from_db
    return ""


def scrape_run_id_from_log(log_path: Path, *, store_name: str) -> str:
    if not log_path.exists():
        return ""
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = SCRAPE_RUN_ID_RE.search(line)
            if not match:
                continue
            scrape_run_id = match.group("scrape_run_id")
            if not store_name or scrape_run_id.startswith(f"{store_name}:"):
                return scrape_run_id
    except OSError:
        return ""
    return ""


def scrape_run_id_from_db(run: dict[str, Any]) -> str:
    db_path = runner.db_path
    if not db_path.exists():
        return ""
    store_name = str(run.get("store") or "")
    started_at = _parse_iso(str(run.get("started_at") or ""))
    expected_items = int(run.get("items_persisted") or run.get("items_scraped") or 0)
    if not store_name or started_at is None:
        return ""
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(db_path))
        cursor = connection.cursor()
        rows = cursor.execute(
            "select run_id, started_at from scrape_runs where store_name = ? order by id desc limit 50",
            (store_name,),
        ).fetchall()
        candidates: list[tuple[float, str]] = []
        for scrape_run_id, db_started_at in rows:
            db_started = _parse_iso(str(db_started_at or ""))
            if db_started is None:
                continue
            delta = abs((db_started - started_at).total_seconds())
            if delta > 300:
                continue
            if expected_items:
                count = cursor.execute(
                    "select count(*) from raw_products where scrape_run_id = ?",
                    (scrape_run_id,),
                ).fetchone()[0]
                if int(count) != expected_items:
                    continue
            candidates.append((delta, str(scrape_run_id)))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]
    except sqlite3.Error:
        return ""
    finally:
        if connection is not None:
            connection.close()


def patch_run_scrape_id(run: dict[str, Any], scrape_run_id: str) -> None:
    summary = dict(run.get("summary") or {})
    summary["scrape_run_id"] = scrape_run_id
    registry.patch(str(run.get("id")), {"scrape_run_id": scrape_run_id, "summary": summary})


def publish_once() -> dict[str, int]:
    config = PublisherServiceConfig(
        rabbitmq_url=settings.RABBITMQ_URL,
        exchange_name=settings.RABBITMQ_EXCHANGE,
        exchange_type=settings.RABBITMQ_EXCHANGE_TYPE,
        queue_name=settings.RABBITMQ_QUEUE,
        routing_key=settings.RABBITMQ_ROUTING_KEY,
        publish_mandatory=settings.RABBITMQ_PUBLISH_MANDATORY,
        declare_topology=settings.RABBITMQ_DECLARE_TOPOLOGY,
        heartbeat_seconds=settings.RABBITMQ_HEARTBEAT_SECONDS,
        connection_name="ui-publisher-once",
        batch_size=settings.SCRAPER_OUTBOX_BATCH_SIZE,
        lease_seconds=settings.SCRAPER_OUTBOX_LEASE_SECONDS,
        max_retries=settings.SCRAPER_OUTBOX_MAX_RETRIES,
        retry_base_seconds=settings.SCRAPER_OUTBOX_RETRY_BASE_SECONDS,
        poll_interval_seconds=settings.PUBLISHER_POLL_INTERVAL_SECONDS,
        publisher_service_name="ui-publisher",
        scraper_db_backend="sqlite",
        scraper_db_dsn="",
        scraper_db_path=str(runner.db_path),
    )

    async def _run_once() -> dict[str, int]:
        worker = PublicationWorker(config=config)
        try:
            result = await worker.run_once()
            return {"claimed": result.claimed, "published": result.published, "failed": result.failed}
        finally:
            await worker.aclose()

    return asyncio.run(_run_once())


def format_log_line(line: str) -> dict[str, str]:
    level = "INFO"
    if " ERROR:" in line or " ERROR " in line:
        level = "ERROR"
    elif " WARNING:" in line or " WARN " in line:
        level = "WARN"
    timestamp = ""
    message = line
    parts = line.split(" ", 2)
    if len(parts) >= 3 and parts[0].startswith("20"):
        timestamp = parts[1]
        message = parts[2]
    return {"timestamp": timestamp, "level": level, "message": compact_log_message(message)}


def is_internal_noise(line: str) -> bool:
    noisy_markers = (
        '"message_code": "FEATURE_ROLLOUT_DECIDED"',
        '"message_code": "RESOURCE_ADMISSION_ALLOWED"',
        '"event": "REQUEST_MODE_SELECTED"',
        '"observability": "parser_resource_gov_v1"',
        '"run_id": "rollout_policy"',
    )
    return any(marker in line for marker in noisy_markers)


def compact_log_message(message: str) -> str:
    replacements = {
        "crawl_framework ": "",
        "sync_event ": "",
        "access_layer ": "",
        "resource_gov_event ": "",
    }
    for old, new in replacements.items():
        message = message.replace(old, new, 1)
    if "UI_RUN_FINISH" in message:
        return message[message.index("UI_RUN_FINISH") :]
    if "scraper_db_saved" in message:
        return message[message.index("scraper_db_saved") :]
    structured = compact_structured_json_message(message)
    if structured:
        return structured
    return message


def compact_structured_json_message(message: str) -> str | None:
    json_start = message.find("{")
    if json_start < 0:
        return None
    try:
        payload = json.loads(message[json_start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    event = payload.get("event") or payload.get("message_code")
    if not event:
        return None
    correlation = payload.get("correlation") if isinstance(payload.get("correlation"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    store = payload.get("store") or payload.get("spider") or correlation.get("store_name") or details.get("store_name")
    page = payload.get("page") or metrics.get("page")
    count = payload.get("extracted_count") or metrics.get("product_links")
    source_id = payload.get("source_id") or correlation.get("source_id")
    url = (
        payload.get("canonical_url")
        or payload.get("source_url")
        or payload.get("category_url")
        or correlation.get("source_url")
        or correlation.get("category_url")
    )

    parts = [str(event)]
    if store and store != "*":
        parts.append(f"store={store}")
    if page is not None:
        parts.append(f"page={page}")
    if count is not None:
        parts.append(f"items={count}")
    if source_id:
        parts.append(f"source_id={source_id}")
    if url:
        parts.append(f"url={url}")
    return " ".join(parts)


def diagnostics_payload() -> dict[str, Any]:
    db_backend = settings.resolved_scraper_db_backend()
    db_status = "available"
    rabbit_status = "available" if _rabbitmq_available() else "unavailable"
    return {
        "stores": list(settings.STORE_NAMES),
        "dbBackend": db_backend,
        "dbStatus": db_status,
        "rabbitmqStatus": rabbit_status,
        "pythonVersion": ".".join(str(part) for part in sys.version_info[:3]),
        "lastRunLogPath": _last_log_path(),
        "scrapyAvailable": _scrapy_available(),
        "uiRegistryPath": str(REGISTRY_PATH),
    }


def _rabbitmq_available() -> bool:
    parsed = urlsplit(settings.RABBITMQ_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5672
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _scrapy_available() -> bool:
    try:
        import scrapy  # noqa: F401

        return True
    except Exception:
        return False


def _last_log_path() -> str:
    logs = sorted((REPO_ROOT / "data" / "ui" / "logs").glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    return str(logs[0]) if logs else ""


def _optional_positive_int(value: object) -> int | None:
    if value in (None, "", False):
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("limits must be greater than zero")
    return parsed


def _optional_nonnegative_int(value: object) -> int | None:
    if value in (None, "", False):
        return None
    parsed = int(value)
    return max(0, parsed)


def _optional_positive_float(value: object) -> float | None:
    if value in (None, "", False):
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("parse interval must be greater than zero")
    return parsed


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_iso(value: str) -> Any:
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Moscraper operator UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), UIRequestHandler)
    print(f"Moscraper UI listening on http://{args.host}:{args.port}")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
