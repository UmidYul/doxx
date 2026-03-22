from __future__ import annotations

import logging

from config.settings import settings
from infrastructure.transports.base import BaseTransport

logger = logging.getLogger(__name__)


def get_transport() -> BaseTransport:
    """Instantiate the transport configured by ``TRANSPORT_TYPE``.

    ``MOSCRAPER_DISABLE_PUBLISH=true`` overrides to the disabled transport
    regardless of ``TRANSPORT_TYPE`` (backward compat with test harness).

    When ``DEV_MODE=true`` and ``DEV_DRY_RUN_DISABLE_CRM_SEND=true`` and
    ``TRANSPORT_TYPE=crm_http``, uses :class:`DryRunTransport` so the sync
    pipeline runs without real CRM HTTP (9B). Production keeps ``DEV_MODE=false``.
    """
    transport_type = settings.TRANSPORT_TYPE.lower()

    if settings.MOSCRAPER_DISABLE_PUBLISH or transport_type == "disabled":
        from infrastructure.transports.disabled import DisabledTransport

        logger.info("Transport: disabled")
        return DisabledTransport()

    if (
        transport_type == "crm_http"
        and getattr(settings, "DEV_MODE", False)
        and getattr(settings, "DEV_DRY_RUN_DISABLE_CRM_SEND", True)
    ):
        from infrastructure.transports.dry_run import DryRunTransport

        logger.info("Transport: CRM dry-run (DEV_MODE, no real HTTP)")
        return DryRunTransport()

    if transport_type == "crm_http":
        from infrastructure.transports.crm_http import CrmHttpTransport

        logger.info("Transport: CRM HTTP → %s", settings.CRM_BASE_URL)
        return CrmHttpTransport()

    if transport_type == "rabbitmq":
        from infrastructure.transports.rabbitmq import RabbitMQTransport

        logger.info("Transport: RabbitMQ (legacy) → %s", settings.RABBITMQ_URL)
        return RabbitMQTransport()

    raise ValueError(f"Unsupported TRANSPORT_TYPE: {settings.TRANSPORT_TYPE!r}")
