from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from application.dev.debug_summary import (
    build_lifecycle_debug_view,
    build_normalized_debug_view,
)
from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle
from config.settings import settings
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_developer_experience_event
from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def _load(path: str) -> dict[str, object]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Fixture must be a JSON object: {path}")
    return data


def _normalize_item_from_fixture(data: dict[str, object], store_name: str) -> dict[str, object]:
    if "raw_item" in data:
        item = dict(data["raw_item"])  # type: ignore[arg-type]
    else:
        item = dict(data)
    src = (item.get("source") or store_name or "mediapark").strip()
    item["source"] = src
    spider = MagicMock(store_name=store_name or src)
    NormalizePipeline().process_item(item, spider)
    norm = item.get("_normalized")
    if not isinstance(norm, dict):
        raise ValueError("Normalization did not produce _normalized")
    return norm


def replay_listing_fixture(path: str, store_name: str) -> dict[str, object]:
    """Replay a crawl-shaped listing fixture through normalization (no live CRM)."""
    log_developer_experience_event(
        obs_mc.DEV_FIXTURE_REPLAY_STARTED,
        dev_run_mode="fixture_replay",
        store_name=store_name,
        fixture_name=Path(path).name,
        details={"kind": "listing"},
    )
    data = _load(path)
    norm = _normalize_item_from_fixture(data, store_name)
    dbg = build_normalized_debug_view(norm, settings)
    return {
        "kind": "listing_replay_v1",
        "fixture_path": path,
        "store_name": store_name,
        "normalized": norm,
        "debug": dbg,
    }


def replay_product_fixture(path: str, store_name: str) -> dict[str, object]:
    """Replay a product-shaped fixture through normalization (no live CRM)."""
    log_developer_experience_event(
        obs_mc.DEV_FIXTURE_REPLAY_STARTED,
        dev_run_mode="fixture_replay",
        store_name=store_name,
        fixture_name=Path(path).name,
        details={"kind": "product"},
    )
    data = _load(path)
    norm = _normalize_item_from_fixture(data, store_name)
    dbg = build_normalized_debug_view(norm, settings)
    return {
        "kind": "product_replay_v1",
        "fixture_path": path,
        "store_name": store_name,
        "normalized": norm,
        "debug": dbg,
    }


def replay_normalization_fixture(path: str) -> dict[str, object]:
    """Load a regression normalization JSON (``raw_item``) and return normalized + debug view."""
    log_developer_experience_event(
        obs_mc.DEV_FIXTURE_REPLAY_STARTED,
        dev_run_mode="fixture_replay",
        fixture_name=Path(path).name,
        details={"kind": "normalization"},
    )
    data = _load(path)
    raw = data.get("raw_item")
    if not isinstance(raw, dict):
        raise ValueError("Fixture must contain a 'raw_item' object")
    store = str(raw.get("source") or "mediapark").strip()
    norm = _normalize_item_from_fixture(data, store)
    dbg = build_normalized_debug_view(norm, settings)
    return {
        "kind": "normalization_replay_v1",
        "fixture_path": path,
        "category": data.get("category"),
        "normalized": norm,
        "debug": dbg,
    }


def replay_lifecycle_fixture(path: str) -> dict[str, object]:
    """Build lifecycle + parser sync preview from normalized data in a fixture (no CRM)."""
    log_developer_experience_event(
        obs_mc.DEV_FIXTURE_REPLAY_STARTED,
        dev_run_mode="fixture_replay",
        fixture_name=Path(path).name,
        details={"kind": "lifecycle"},
    )
    data = _load(path)
    if "normalized" in data and isinstance(data["normalized"], dict):
        normalized = dict(data["normalized"])  # type: ignore[arg-type]
        runtime_ids = data.get("runtime_ids")
        rid = runtime_ids if isinstance(runtime_ids, dict) else None
    elif "raw_item" in data:
        raw = data["raw_item"]
        src = str((raw.get("source") if isinstance(raw, dict) else None) or data.get("store") or "mediapark")
        normalized = _normalize_item_from_fixture(data, src)
        rid = data.get("runtime_ids")
        rid = rid if isinstance(rid, dict) else None
    else:
        raise ValueError("Fixture needs 'normalized' or 'raw_item'")

    ple, decision = build_lifecycle_event(normalized, rid, None)
    sync_ev = parser_sync_event_from_lifecycle(ple, normalized_for_reconcile=dict(normalized))
    ev_dump = ple.model_dump(mode="json")
    dec_dump = decision.model_dump(mode="json")
    sync_dump = sync_ev.model_dump(mode="json")
    return {
        "kind": "lifecycle_replay_v1",
        "fixture_path": path,
        "lifecycle_event": ev_dump,
        "decision": dec_dump,
        "parser_sync_event": sync_dump,
        "debug": build_lifecycle_debug_view(ev_dump, dec_dump),
    }
