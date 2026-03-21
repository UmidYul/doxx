from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_only_dot_env_example_exists_as_template():
    assert (REPO_ROOT / ".env.example").is_file()
    assert not (REPO_ROOT / "env.example").is_file()


def test_dot_env_example_documents_broker_and_core_keys():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "RABBITMQ_URL",
        "RABBITMQ_EXCHANGE",
        "RABBITMQ_EXCHANGE_TYPE",
        "RABBITMQ_ROUTING_KEY",
        "SENTRY_DSN",
        "MOSCRAPER_DISABLE_PUBLISH",
        "STORE_NAMES",
    ):
        assert key in text
