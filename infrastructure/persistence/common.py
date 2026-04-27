from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import orjson

from config.settings import settings
from domain.scrape_fingerprints import normalize_text


@dataclass(slots=True)
class FlattenedSpec:
    spec_name: str
    spec_value: str
    source_section: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def isoformat_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def json_dumps(payload: object) -> str:
    return orjson.dumps(payload).decode("utf-8")


def json_loads(payload: str) -> object:
    return orjson.loads(payload)


def extract_schema_version(payload: object) -> int:
    if isinstance(payload, str):
        try:
            payload = json_loads(payload)
        except orjson.JSONDecodeError:
            return int(settings.MESSAGE_SCHEMA_VERSION)
    if isinstance(payload, dict):
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, int):
            return schema_version
        publication = payload.get("publication")
        if isinstance(publication, dict):
            publication_version = publication.get("publication_version")
            if isinstance(publication_version, int):
                return publication_version
            contract_version = publication.get("contract_version")
            if isinstance(contract_version, int):
                return contract_version
    return int(settings.MESSAGE_SCHEMA_VERSION)


def flatten_specs(raw_specs: dict[str, Any]) -> list[FlattenedSpec]:
    flattened: list[FlattenedSpec] = []
    for key, value in raw_specs.items():
        clean_key = normalize_text(key)
        if not clean_key:
            continue
        if isinstance(value, dict) and value:
            _flatten_spec_section(flattened, section=clean_key, payload=value, prefix=None)
            continue
        clean_value = coerce_spec_value(value)
        if clean_value is None:
            continue
        flattened.append(FlattenedSpec(spec_name=clean_key, spec_value=clean_value, source_section=None))
    return flattened


def _flatten_spec_section(
    flattened: list[FlattenedSpec],
    *,
    section: str,
    payload: dict[str, Any],
    prefix: str | None,
) -> None:
    for key, value in payload.items():
        clean_key = normalize_text(key)
        if not clean_key:
            continue
        next_prefix = clean_key if prefix is None else f"{prefix} / {clean_key}"
        if isinstance(value, dict) and value:
            _flatten_spec_section(flattened, section=section, payload=value, prefix=next_prefix)
            continue
        clean_value = coerce_spec_value(value)
        if clean_value is None:
            continue
        flattened.append(FlattenedSpec(spec_name=next_prefix, spec_value=clean_value, source_section=section))


def coerce_spec_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return json_dumps(value)
    if isinstance(value, list):
        normalized_items: list[object] = []
        for item in value:
            if isinstance(item, dict):
                normalized_items.append(item)
                continue
            clean_item = normalize_text(item)
            if clean_item:
                normalized_items.append(clean_item)
        if not normalized_items:
            return None
        return json_dumps(normalized_items)
    return normalize_text(value)


def serialize_row_value(value: object) -> object:
    if isinstance(value, datetime):
        return isoformat_utc(value)
    if isinstance(value, (dict, list)):
        return json_dumps(value)
    return value


def serialize_row(row: dict[str, object]) -> dict[str, object]:
    return {key: serialize_row_value(value) for key, value in row.items()}
