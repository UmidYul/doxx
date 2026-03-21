from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_DB_URL: str = ""

    # Same database URI as SUPABASE_DB_URL — used by Alembic (env.py).
    DATABASE_URL_SYNC: str = ""

    @model_validator(mode="after")
    def _default_database_url_sync(self) -> Settings:
        if not (self.DATABASE_URL_SYNC or "").strip() and self.SUPABASE_DB_URL:
            object.__setattr__(self, "DATABASE_URL_SYNC", self.SUPABASE_DB_URL)
        return self

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    CRM_API_URL: str = "http://crm-service/api"
    CRM_API_KEY: str = "secret-parser-key"

    ANTHROPIC_API_KEY: str = ""
    LLM_EXTRACTION_ENABLED: bool = False
    LLM_CACHE_TTL_DAYS: int = 30

    REMBG_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_IMAGES_PER_PRODUCT: int = 5

    PROXY_LIST_PATH: str = ""
    SENTRY_DSN: str = ""

    SPEC_SCORE_THRESHOLD_STRUCTURED: float = 0.7
    SPEC_SCORE_THRESHOLD_REGEX: float = 0.4

    SCRAPY_LOG_LEVEL: str = "INFO"
    SCRAPY_CONCURRENT_REQUESTS: int = 8
    SCRAPY_DOWNLOAD_DELAY: float = 1.5

    STORE_NAMES: list[str] = ["mediapark", "olx", "texnomart", "makro", "uzum"]


settings = Settings()
