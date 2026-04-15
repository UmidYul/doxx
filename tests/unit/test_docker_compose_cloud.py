from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_COMPOSE = REPO_ROOT / "docker-compose.cloud.yml"


def test_cloud_compose_uses_external_rabbitmq_and_keeps_bootstrap_least_privileged():
    text = CLOUD_COMPOSE.read_text(encoding="utf-8")
    assert "moscraper-rabbitmq-bootstrap-cloud" in text
    assert "container_name: moscraper-scraper-cloud" in text
    assert "container_name: moscraper-publisher-cloud" in text
    assert "  rabbitmq:" not in text
    assert "RABBITMQ_URL: ${RABBITMQ_URL}" in text
    assert "RABBITMQ_MANAGEMENT_URL: ${RABBITMQ_MANAGEMENT_URL}" in text
    assert "RABBITMQ_BOOTSTRAP_MANAGE_VHOST: ${RABBITMQ_BOOTSTRAP_MANAGE_VHOST:-false}" in text
    assert "RABBITMQ_BOOTSTRAP_MANAGE_USERS: ${RABBITMQ_BOOTSTRAP_MANAGE_USERS:-false}" in text
    assert "RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS: ${RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS:-false}" in text
    assert 'RABBITMQ_DECLARE_TOPOLOGY: "false"' in text
