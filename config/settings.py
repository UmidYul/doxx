from __future__ import annotations

"""Runtime configuration from environment variables and optional ``.env`` (no DB/Celery/CRM REST)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Broker and scraping knobs. Unknown env keys are ignored (``extra="ignore"``)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    BROKER_TYPE: str = "rabbitmq"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "moscraper.events"
    RABBITMQ_EXCHANGE_TYPE: str = "topic"
    RABBITMQ_ROUTING_KEY: str = "listing.scraped.v1"
    RABBITMQ_PUBLISH_MANDATORY: bool = True
    # 0 = fail fast on publish errors (default). Retries/DLQ belong to CRM/broker.
    MAX_PUBLISH_RETRIES: int = Field(default=0, ge=0)

    DEFAULT_CURRENCY: str = "UZS"
    MESSAGE_SCHEMA_VERSION: int = 1

    # Tests only: build messages but do not connect to RabbitMQ
    MOSCRAPER_DISABLE_PUBLISH: bool = False

    PROXY_LIST_PATH: str = ""
    SENTRY_DSN: str = ""

    SCRAPY_LOG_LEVEL: str = "INFO"
    SCRAPY_CONCURRENT_REQUESTS: int = 8
    SCRAPY_DOWNLOAD_DELAY: float = 1.5

    STORE_NAMES: list[str] = Field(default_factory=lambda: ["mediapark"])


settings = Settings()
