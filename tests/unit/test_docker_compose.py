from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


def test_docker_compose_has_rabbitmq_scraper_and_publisher():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "  rabbitmq:" in text
    assert "  scraper:" in text
    assert "  publisher:" in text
    for other in ("  postgres:", "  redis:", "  adminer:", "  mysql:", "  mongo:"):
        assert other not in text.lower()


def test_rabbitmq_image_and_ports():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "rabbitmq:3-management" in text
    assert "5672:5672" in text
    assert "15672:15672" in text


def test_scraper_build_and_service_commands():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile" in text.replace(" ", "") or "Dockerfile" in text
    assert "context: ." in text or "context:." in text.replace(" ", "")
    assert "RABBITMQ_URL:" in text
    assert "RABBITMQ_EXCHANGE:" in text
    assert "RABBITMQ_QUEUE:" in text
    assert "scrapy" in text and "crawl" in text
    assert "services.publisher.main" in text
    assert "SCRAPER_DB_PATH:" in text
