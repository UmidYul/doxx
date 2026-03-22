from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _parse_dotenv_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def test_settings_has_no_legacy_db_or_broker_field_names():
    fields = set(Settings.model_fields)
    legacy = {
        "SUPABASE_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CRM_API_URL",
    }
    assert legacy.isdisjoint(fields)


def test_settings_instantiates_with_env_example_pairs(monkeypatch: pytest.MonkeyPatch):
    env = _parse_dotenv_lines(ENV_EXAMPLE.read_text(encoding="utf-8"))
    for key, val in env.items():
        monkeypatch.setenv(key, val)
    s = Settings(_env_file=None)
    assert s.RABBITMQ_EXCHANGE == "moscraper.events"
    assert s.BROKER_TYPE == "rabbitmq"
    assert s.MAX_PUBLISH_RETRIES == 0
    assert s.TRANSPORT_TYPE == "crm_http"
    assert s.CRM_SYNC_ENDPOINT == "/api/parser/sync"
    assert s.CRM_BATCH_SIZE == 50


def test_max_publish_retries_must_be_non_negative():
    with pytest.raises(ValidationError):
        Settings(MAX_PUBLISH_RETRIES=-1, _env_file=None)


def test_crm_batch_size_max_100():
    with pytest.raises(ValidationError):
        Settings(CRM_BATCH_SIZE=101, _env_file=None)


def test_transport_type_field_exists():
    fields = set(Settings.model_fields)
    assert "TRANSPORT_TYPE" in fields
    assert "CRM_BASE_URL" in fields
    assert "CRM_PARSER_KEY" in fields
