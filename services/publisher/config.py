from __future__ import annotations

from pydantic import BaseModel, Field

from config.settings import settings


class PublisherServiceConfig(BaseModel):
    rabbitmq_url: str
    exchange_name: str
    exchange_type: str
    queue_name: str
    routing_key: str
    publish_mandatory: bool = True
    declare_topology: bool = False
    heartbeat_seconds: int = Field(ge=1)
    connection_name: str
    batch_size: int = Field(ge=1)
    lease_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=1)
    retry_base_seconds: int = Field(ge=1)
    poll_interval_seconds: float = Field(ge=0.1)
    publisher_service_name: str
    scraper_db_backend: str
    scraper_db_dsn: str = ""
    scraper_db_path: str

    @classmethod
    def from_settings(cls) -> "PublisherServiceConfig":
        return cls(
            rabbitmq_url=settings.RABBITMQ_URL,
            exchange_name=settings.RABBITMQ_EXCHANGE,
            exchange_type=settings.RABBITMQ_EXCHANGE_TYPE,
            queue_name=settings.RABBITMQ_QUEUE,
            routing_key=settings.RABBITMQ_ROUTING_KEY,
            publish_mandatory=settings.RABBITMQ_PUBLISH_MANDATORY,
            declare_topology=settings.RABBITMQ_DECLARE_TOPOLOGY,
            heartbeat_seconds=settings.RABBITMQ_HEARTBEAT_SECONDS,
            connection_name=settings.RABBITMQ_CONNECTION_NAME or settings.PUBLISHER_SERVICE_NAME,
            batch_size=settings.SCRAPER_OUTBOX_BATCH_SIZE,
            lease_seconds=settings.SCRAPER_OUTBOX_LEASE_SECONDS,
            max_retries=settings.SCRAPER_OUTBOX_MAX_RETRIES,
            retry_base_seconds=settings.SCRAPER_OUTBOX_RETRY_BASE_SECONDS,
            poll_interval_seconds=settings.PUBLISHER_POLL_INTERVAL_SECONDS,
            publisher_service_name=settings.PUBLISHER_SERVICE_NAME,
            scraper_db_backend=settings.resolved_scraper_db_backend(),
            scraper_db_dsn=settings.SCRAPER_DB_DSN,
            scraper_db_path=settings.SCRAPER_DB_PATH,
        )
