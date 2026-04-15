from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from config.settings import Settings
from scripts.bootstrap_rabbitmq import RabbitManagementClient, bootstrap_rabbitmq, build_bootstrap_plan


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        RABBITMQ_MANAGEMENT_URL="http://rabbitmq:15672",
        RABBITMQ_ADMIN_USER="moscraper_admin",
        RABBITMQ_ADMIN_PASS="admin-pass",
        RABBITMQ_PUBLISHER_USER="moscraper_publisher",
        RABBITMQ_PUBLISHER_PASS="publisher-pass",
        RABBITMQ_CRM_USER="moscraper_crm",
        RABBITMQ_CRM_PASS="crm-pass",
    )


@dataclass
class _FakeResponse:
    payload: Any = None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class _FakeHttpClient:
    def __init__(self, *, bindings_by_queue: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.bindings_by_queue = bindings_by_queue or {}
        self.puts: list[dict[str, Any]] = []
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []

    def close(self) -> None:
        return None

    def get(self, path: str) -> _FakeResponse:
        self.gets.append(path)
        if path == "/api/overview":
            return _FakeResponse({})
        if path.endswith("/bindings"):
            queue_name = unquote(path.split("/")[-2])
            return _FakeResponse(self.bindings_by_queue.get(queue_name, []))
        return _FakeResponse({})

    def put(self, path: str, json: dict[str, Any]) -> _FakeResponse:
        self.puts.append({"path": path, "json": json})
        return _FakeResponse({})

    def post(self, path: str, json: dict[str, Any]) -> _FakeResponse:
        self.posts.append({"path": path, "json": json})
        return _FakeResponse({})


def test_build_bootstrap_plan_contains_retry_lanes_and_permissions() -> None:
    cfg = _settings()
    plan = build_bootstrap_plan(cfg)

    queue_map = {queue.name: queue for queue in plan.queues}
    assert queue_map["crm.products.import.v1"].arguments == {
        "x-dead-letter-exchange": "crm.products.dlx",
        "x-dead-letter-routing-key": "dead",
    }
    assert queue_map["crm.products.import.v1.retry.30s"].arguments["x-message-ttl"] == 30000
    assert queue_map["crm.products.import.v1.retry.5m"].arguments["x-message-ttl"] == 300000
    assert queue_map["crm.products.import.v1.retry.30m"].arguments["x-message-ttl"] == 1800000

    publisher = next(user for user in plan.users if user.username == "moscraper_publisher")
    crm = next(user for user in plan.users if user.username == "moscraper_crm")
    assert publisher.permissions is not None
    assert publisher.permissions.configure == "^$"
    assert publisher.permissions.write == "^moscraper\\.events$"
    assert crm.permissions is not None
    assert crm.permissions.write == "^crm\\.products\\.retry$"
    assert crm.permissions.read == "^(crm\\.products\\.import\\.v1|crm\\.products\\.import\\.v1\\.dlq)$"


def test_bootstrap_rabbitmq_is_idempotent_for_existing_bindings() -> None:
    cfg = _settings()
    fake_http = _FakeHttpClient(
        bindings_by_queue={
            "scraper.products.v1": [
                {
                    "source": "moscraper.events",
                    "destination": "scraper.products.v1",
                    "routing_key": "listing.scraped.v1",
                }
            ],
            "crm.products.import.v1": [
                {
                    "source": "moscraper.events",
                    "destination": "crm.products.import.v1",
                    "routing_key": "listing.scraped.v1",
                },
                {
                    "source": "crm.products.requeue",
                    "destination": "crm.products.import.v1",
                    "routing_key": "main",
                },
            ],
        }
    )
    management = RabbitManagementClient(
        base_url=cfg.RABBITMQ_MANAGEMENT_URL,
        username=cfg.RABBITMQ_ADMIN_USER,
        password=cfg.RABBITMQ_ADMIN_PASS,
        client=fake_http,
    )

    plan = bootstrap_rabbitmq(cfg, management=management)

    assert plan.vhost == "moscraper"
    permission_paths = [call["path"] for call in fake_http.puts if "/api/permissions/" in call["path"]]
    assert len(permission_paths) == 3

    post_paths = [call["path"] for call in fake_http.posts]
    assert "/api/bindings/moscraper/e/moscraper.events/q/scraper.products.v1" not in post_paths
    assert "/api/bindings/moscraper/e/moscraper.events/q/crm.products.import.v1" not in post_paths
    assert "/api/bindings/moscraper/e/crm.products.retry/q/crm.products.import.v1.retry.30s" in post_paths
    assert "/api/bindings/moscraper/e/crm.products.dlx/q/crm.products.import.v1.dlq" in post_paths


def test_bootstrap_rabbitmq_shared_mode_skips_vhost_users_and_permissions() -> None:
    cfg = Settings(
        _env_file=None,
        RABBITMQ_MANAGEMENT_URL="https://example.rmq.cloudamqp.com",
        RABBITMQ_ADMIN_USER="shared-user",
        RABBITMQ_ADMIN_PASS="shared-pass",
        RABBITMQ_PUBLISHER_USER="shared-user",
        RABBITMQ_PUBLISHER_PASS="shared-pass",
        RABBITMQ_CRM_USER="shared-user",
        RABBITMQ_CRM_PASS="shared-pass",
        RABBITMQ_BOOTSTRAP_MANAGE_VHOST=False,
        RABBITMQ_BOOTSTRAP_MANAGE_USERS=False,
        RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS=False,
    )
    fake_http = _FakeHttpClient()
    management = RabbitManagementClient(
        base_url=cfg.RABBITMQ_MANAGEMENT_URL,
        username=cfg.RABBITMQ_ADMIN_USER,
        password=cfg.RABBITMQ_ADMIN_PASS,
        client=fake_http,
    )

    bootstrap_rabbitmq(cfg, management=management)

    put_paths = [call["path"] for call in fake_http.puts]
    assert not any(path.startswith("/api/vhosts/") for path in put_paths)
    assert not any(path.startswith("/api/users/") for path in put_paths)
    assert not any(path.startswith("/api/permissions/") for path in put_paths)
    assert any(path.startswith("/api/exchanges/") for path in put_paths)
    assert any(path.startswith("/api/queues/") for path in put_paths)
