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
    batch_size: int = Field(ge=1)
    lease_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=1)
    retry_base_seconds: int = Field(ge=1)
    poll_interval_seconds: float = Field(ge=0.1)
    publisher_service_name: str
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
            batch_size=settings.SCRAPER_OUTBOX_BATCH_SIZE,
            lease_seconds=settings.SCRAPER_OUTBOX_LEASE_SECONDS,
            max_retries=settings.SCRAPER_OUTBOX_MAX_RETRIES,
            retry_base_seconds=settings.SCRAPER_OUTBOX_RETRY_BASE_SECONDS,
            poll_interval_seconds=settings.PUBLISHER_POLL_INTERVAL_SECONDS,
            publisher_service_name=settings.PUBLISHER_SERVICE_NAME,
            scraper_db_path=settings.SCRAPER_DB_PATH,
        )
