from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from config.settings import Settings, settings

DEFAULT_WAIT_SECONDS = 60.0
DEFAULT_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class RabbitPermissionSpec:
    username: str
    configure: str
    write: str
    read: str


@dataclass(frozen=True)
class RabbitUserSpec:
    username: str
    password: str
    tags: str = ""
    permissions: RabbitPermissionSpec | None = None


@dataclass(frozen=True)
class RabbitExchangeSpec:
    name: str
    exchange_type: str
    durable: bool = True
    auto_delete: bool = False
    internal: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RabbitQueueSpec:
    name: str
    durable: bool = True
    auto_delete: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RabbitBindingSpec:
    source: str
    destination: str
    routing_key: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RabbitBootstrapPlan:
    vhost: str
    users: tuple[RabbitUserSpec, ...]
    exchanges: tuple[RabbitExchangeSpec, ...]
    queues: tuple[RabbitQueueSpec, ...]
    bindings: tuple[RabbitBindingSpec, ...]


def _quote(value: str) -> str:
    return quote(value, safe="")


def _regex_escape(value: str) -> str:
    return re.escape(value)


def _normalize_management_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        normalized = normalized[:-4]
    return normalized


def build_bootstrap_plan(cfg: Settings) -> RabbitBootstrapPlan:
    crm_queue = cfg.RABBITMQ_CRM_QUEUE
    retry_30s_queue = f"{crm_queue}.retry.30s"
    retry_5m_queue = f"{crm_queue}.retry.5m"
    retry_30m_queue = f"{crm_queue}.retry.30m"
    dlq_queue = f"{crm_queue}.dlq"

    admin = RabbitUserSpec(
        username=cfg.RABBITMQ_ADMIN_USER,
        password=cfg.RABBITMQ_ADMIN_PASS,
        tags="administrator",
        permissions=RabbitPermissionSpec(
            username=cfg.RABBITMQ_ADMIN_USER,
            configure=".*",
            write=".*",
            read=".*",
        ),
    )
    publisher = RabbitUserSpec(
        username=cfg.RABBITMQ_PUBLISHER_USER,
        password=cfg.RABBITMQ_PUBLISHER_PASS,
        permissions=RabbitPermissionSpec(
            username=cfg.RABBITMQ_PUBLISHER_USER,
            configure="^$",
            write=f"^{_regex_escape(cfg.RABBITMQ_EXCHANGE)}$",
            read="^$",
        ),
    )
    crm = RabbitUserSpec(
        username=cfg.RABBITMQ_CRM_USER,
        password=cfg.RABBITMQ_CRM_PASS,
        permissions=RabbitPermissionSpec(
            username=cfg.RABBITMQ_CRM_USER,
            configure="^$",
            write=f"^{_regex_escape(cfg.RABBITMQ_RETRY_EXCHANGE)}$",
            read=f"^({_regex_escape(crm_queue)}|{_regex_escape(dlq_queue)})$",
        ),
    )

    exchanges = (
        RabbitExchangeSpec(name=cfg.RABBITMQ_EXCHANGE, exchange_type=cfg.RABBITMQ_EXCHANGE_TYPE),
        RabbitExchangeSpec(name=cfg.RABBITMQ_RETRY_EXCHANGE, exchange_type="direct"),
        RabbitExchangeSpec(name=cfg.RABBITMQ_REQUEUE_EXCHANGE, exchange_type="direct"),
        RabbitExchangeSpec(name=cfg.RABBITMQ_DLX_EXCHANGE, exchange_type="direct"),
    )
    queues = (
        RabbitQueueSpec(name=cfg.RABBITMQ_QUEUE),
        RabbitQueueSpec(
            name=crm_queue,
            arguments={
                "x-dead-letter-exchange": cfg.RABBITMQ_DLX_EXCHANGE,
                "x-dead-letter-routing-key": "dead",
            },
        ),
        RabbitQueueSpec(
            name=retry_30s_queue,
            arguments={
                "x-message-ttl": cfg.RABBITMQ_RETRY_30S_MS,
                "x-dead-letter-exchange": cfg.RABBITMQ_REQUEUE_EXCHANGE,
                "x-dead-letter-routing-key": "main",
            },
        ),
        RabbitQueueSpec(
            name=retry_5m_queue,
            arguments={
                "x-message-ttl": cfg.RABBITMQ_RETRY_5M_MS,
                "x-dead-letter-exchange": cfg.RABBITMQ_REQUEUE_EXCHANGE,
                "x-dead-letter-routing-key": "main",
            },
        ),
        RabbitQueueSpec(
            name=retry_30m_queue,
            arguments={
                "x-message-ttl": cfg.RABBITMQ_RETRY_30M_MS,
                "x-dead-letter-exchange": cfg.RABBITMQ_REQUEUE_EXCHANGE,
                "x-dead-letter-routing-key": "main",
            },
        ),
        RabbitQueueSpec(name=dlq_queue),
    )
    bindings = (
        RabbitBindingSpec(
            source=cfg.RABBITMQ_EXCHANGE,
            destination=cfg.RABBITMQ_QUEUE,
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
        ),
        RabbitBindingSpec(
            source=cfg.RABBITMQ_EXCHANGE,
            destination=crm_queue,
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
        ),
        RabbitBindingSpec(source=cfg.RABBITMQ_RETRY_EXCHANGE, destination=retry_30s_queue, routing_key="30s"),
        RabbitBindingSpec(source=cfg.RABBITMQ_RETRY_EXCHANGE, destination=retry_5m_queue, routing_key="5m"),
        RabbitBindingSpec(source=cfg.RABBITMQ_RETRY_EXCHANGE, destination=retry_30m_queue, routing_key="30m"),
        RabbitBindingSpec(source=cfg.RABBITMQ_REQUEUE_EXCHANGE, destination=crm_queue, routing_key="main"),
        RabbitBindingSpec(source=cfg.RABBITMQ_DLX_EXCHANGE, destination=dlq_queue, routing_key="dead"),
    )
    return RabbitBootstrapPlan(
        vhost=cfg.RABBITMQ_VHOST,
        users=(admin, publisher, crm),
        exchanges=exchanges,
        queues=queues,
        bindings=bindings,
    )


class RabbitManagementClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=_normalize_management_base_url(base_url),
            auth=(username, password),
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "RabbitManagementClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def wait_until_ready(
        self,
        *,
        max_wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        deadline = time.monotonic() + max_wait_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = self._client.get("/api/overview")
                response.raise_for_status()
                return
            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                time.sleep(poll_interval_seconds)
        raise RuntimeError("RabbitMQ management API did not become ready in time") from last_error

    def ensure_vhost(self, vhost: str) -> None:
        self._put(f"/api/vhosts/{_quote(vhost)}", {})

    def ensure_user(self, spec: RabbitUserSpec) -> None:
        self._put(
            f"/api/users/{_quote(spec.username)}",
            {
                "password": spec.password,
                "tags": spec.tags,
            },
        )

    def ensure_permissions(self, *, vhost: str, spec: RabbitPermissionSpec) -> None:
        self._put(
            f"/api/permissions/{_quote(vhost)}/{_quote(spec.username)}",
            {
                "configure": spec.configure,
                "write": spec.write,
                "read": spec.read,
            },
        )

    def ensure_exchange(self, *, vhost: str, spec: RabbitExchangeSpec) -> None:
        self._put(
            f"/api/exchanges/{_quote(vhost)}/{_quote(spec.name)}",
            {
                "type": spec.exchange_type,
                "durable": spec.durable,
                "auto_delete": spec.auto_delete,
                "internal": spec.internal,
                "arguments": spec.arguments,
            },
        )

    def ensure_queue(self, *, vhost: str, spec: RabbitQueueSpec) -> None:
        self._put(
            f"/api/queues/{_quote(vhost)}/{_quote(spec.name)}",
            {
                "durable": spec.durable,
                "auto_delete": spec.auto_delete,
                "arguments": spec.arguments,
            },
        )

    def get_queue(self, *, vhost: str, queue_name: str) -> dict[str, Any] | None:
        response = self._client.get(f"/api/queues/{_quote(vhost)}/{_quote(queue_name)}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def delete_queue(self, *, vhost: str, queue_name: str) -> None:
        response = self._client.delete(f"/api/queues/{_quote(vhost)}/{_quote(queue_name)}")
        response.raise_for_status()

    def list_queue_bindings(self, *, vhost: str, queue_name: str) -> list[dict[str, Any]]:
        response = self._client.get(f"/api/queues/{_quote(vhost)}/{_quote(queue_name)}/bindings")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def ensure_binding(self, *, vhost: str, spec: RabbitBindingSpec) -> bool:
        existing = self.list_queue_bindings(vhost=vhost, queue_name=spec.destination)
        for binding in existing:
            if (
                str(binding.get("source")) == spec.source
                and str(binding.get("destination")) == spec.destination
                and str(binding.get("routing_key") or "") == spec.routing_key
            ):
                return False
        response = self._client.post(
            f"/api/bindings/{_quote(vhost)}/e/{_quote(spec.source)}/q/{_quote(spec.destination)}",
            json={
                "routing_key": spec.routing_key,
                "arguments": spec.arguments,
            },
        )
        response.raise_for_status()
        return True

    def _put(self, path: str, payload: dict[str, Any]) -> None:
        response = self._client.put(path, json=payload)
        response.raise_for_status()


def bootstrap_rabbitmq(
    cfg: Settings | None = None,
    *,
    management: RabbitManagementClient | None = None,
) -> RabbitBootstrapPlan:
    runtime = cfg or settings
    plan = build_bootstrap_plan(runtime)
    owns_management = management is None
    manager = management or RabbitManagementClient(
        base_url=runtime.RABBITMQ_MANAGEMENT_URL,
        username=runtime.RABBITMQ_ADMIN_USER,
        password=runtime.RABBITMQ_ADMIN_PASS,
    )
    try:
        manager.wait_until_ready()
        if runtime.RABBITMQ_BOOTSTRAP_MANAGE_VHOST:
            manager.ensure_vhost(plan.vhost)
        for user in plan.users:
            if runtime.RABBITMQ_BOOTSTRAP_MANAGE_USERS:
                manager.ensure_user(user)
            if runtime.RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS and user.permissions is not None:
                manager.ensure_permissions(vhost=plan.vhost, spec=user.permissions)
        for exchange in plan.exchanges:
            manager.ensure_exchange(vhost=plan.vhost, spec=exchange)
        for queue in plan.queues:
            try:
                manager.ensure_queue(vhost=plan.vhost, spec=queue)
            except httpx.HTTPStatusError as exc:
                recreate_allowed = bool(runtime.RABBITMQ_BOOTSTRAP_RECREATE_MISMATCHED_QUEUES)
                existing = manager.get_queue(vhost=plan.vhost, queue_name=queue.name)
                if (
                    exc.response.status_code == 400
                    and recreate_allowed
                    and existing is not None
                    and int(existing.get("messages", 0)) == 0
                    and int(existing.get("messages_ready", 0)) == 0
                    and int(existing.get("messages_unacknowledged", 0)) == 0
                ):
                    manager.delete_queue(vhost=plan.vhost, queue_name=queue.name)
                    manager.ensure_queue(vhost=plan.vhost, spec=queue)
                    continue
                existing_args = {} if existing is None else dict(existing.get("arguments") or {})
                raise RuntimeError(
                    "RabbitMQ queue arguments mismatch for "
                    f"{queue.name}. Existing arguments={existing_args!r}; expected={queue.arguments!r}. "
                    "Drain/delete the queue manually or rerun with "
                    "RABBITMQ_BOOTSTRAP_RECREATE_MISMATCHED_QUEUES=true if it is empty."
                ) from exc
        for binding in plan.bindings:
            manager.ensure_binding(vhost=plan.vhost, spec=binding)
        return plan
    finally:
        if owns_management:
            manager.close()


def _plan_summary(plan: RabbitBootstrapPlan) -> dict[str, Any]:
    return {
        "vhost": plan.vhost,
        "users": [user.username for user in plan.users],
        "exchanges": [exchange.name for exchange in plan.exchanges],
        "queues": [queue.name for queue in plan.queues],
        "bindings": [
            {
                "source": binding.source,
                "destination": binding.destination,
                "routing_key": binding.routing_key,
            }
            for binding in plan.bindings
        ],
    }


def main() -> int:
    plan = bootstrap_rabbitmq()
    print(json.dumps(_plan_summary(plan), ensure_ascii=True, indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
