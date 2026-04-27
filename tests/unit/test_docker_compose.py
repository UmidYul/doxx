from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


def test_docker_compose_has_rabbitmq_bootstrap_db_bootstrap_scraper_job_and_publisher():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "  rabbitmq:" in text
    assert "  rabbitmq-bootstrap:" in text
    assert "  scraper-db-bootstrap:" in text
    assert "  scraper-job:" in text
    assert "  publisher:" in text
    for other in ("  postgres:", "  redis:", "  adminer:", "  mysql:", "  mongo:"):
        assert other not in text.lower()


def test_rabbitmq_ports_are_split_between_lan_amqp_and_local_management():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "rabbitmq:3-management" in text
    assert "${RABBITMQ_AMQP_BIND_HOST:-0.0.0.0}:5672:5672" in text
    assert "${RABBITMQ_MANAGEMENT_BIND_HOST:-127.0.0.1}:15672:15672" in text


def test_scraper_job_and_publisher_wait_for_bootstrap_and_disable_runtime_topology_declare():
    text = COMPOSE.read_text(encoding="utf-8")
    assert 'condition: service_completed_successfully' in text
    assert 'command: ["python", "-m", "scripts.bootstrap_rabbitmq"]' in text
    assert 'command: ["python", "-m", "scripts.bootstrap_scraper_db"]' in text
    assert 'RABBITMQ_DECLARE_TOPOLOGY: "false"' in text
    assert "RABBITMQ_CRM_QUEUE:" in text
    assert "services.publisher.main" in text
    assert "SCRAPER_DB_DSN:" in text
    assert "SCRAPER_DB_MIGRATION_DSN:" in text
