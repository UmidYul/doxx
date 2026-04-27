from __future__ import annotations

"""Runtime configuration for the active scraper/publisher contour plus legacy migration knobs."""

from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _replace_rabbitmq_url_credentials(url: str, *, username: str, password: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        return url
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if parts.port is not None:
        hostname = f"{hostname}:{parts.port}"
    userinfo = quote(username, safe="")
    if password:
        userinfo = f"{userinfo}:{quote(password, safe='')}"
    netloc = f"{userinfo}@{hostname}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Settings(BaseSettings):
    """Transport, CRM, broker, and scraping knobs.  Unknown env keys are ignored."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Legacy transport layer (inactive in the scraper runtime) ---
    TRANSPORT_TYPE: str = "crm_http"
    TRANSPORT_FAIL_FAST: bool = True

    # --- Legacy CRM HTTP transport ---
    CRM_BASE_URL: str = ""
    CRM_PARSER_KEY: str = ""
    CRM_SYNC_ENDPOINT: str = "/api/parser/sync"
    CRM_SYNC_BATCH_ENDPOINT: str = "/api/parser/sync/batch"
    CRM_CATALOG_FIND_ENDPOINT: str = "/api/parser/catalog/find"
    CRM_HTTP_TIMEOUT_SECONDS: float = 15.0
    CRM_HTTP_RETRY_ATTEMPTS: int = Field(default=3, ge=0)
    CRM_HTTP_RETRY_BACKOFF_SECONDS: float = 1.5
    CRM_BATCH_SIZE: int = Field(default=50, ge=1, le=100)

    # --- Parser event & delivery policy (1C) ---
    PARSER_EVENT_DEFAULT_TYPE: str = "product_found"
    PARSER_ENABLE_DELTA_EVENTS: bool = False
    PARSER_ENABLE_PRICE_CHANGED_EVENT: bool = False
    PARSER_ENABLE_OUT_OF_STOCK_EVENT: bool = False
    PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT: bool = False
    SYNC_DEDUPE_IN_MEMORY: bool = True
    SYNC_BUFFER_FLUSH_SECONDS: float = 5.0
    SYNC_MAX_IN_MEMORY_CACHE: int = Field(default=10000, ge=0)
    SYNC_ALLOW_PARTIAL_BATCH_SUCCESS: bool = True

    # --- CRM lifecycle / identity contract (4A) ---
    PARSER_LIFECYCLE_DEFAULT_EVENT: str = "product_found"
    PARSER_ENABLE_RUNTIME_DELTA_EVENTS: bool = False
    PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS: bool = True
    PARSER_ALLOW_OUT_OF_STOCK_WITH_RUNTIME_IDS: bool = True
    PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS: bool = False
    PARSER_FORCE_PRODUCT_FOUND_FALLBACK: bool = True
    PARSER_USE_CATALOG_FIND_PRECHECK: bool = False

    # --- CRM batch / apply semantics (4B) ---
    CRM_BATCH_REQUIRE_ITEM_RESULTS: bool = True
    CRM_BATCH_RETRY_ONLY_RETRYABLE_ITEMS: bool = True
    CRM_BATCH_REQUEUE_RETRYABLE_ITEMS: bool = True
    CRM_BATCH_MAX_RETRYABLE_ITEMS_PER_FLUSH: int = Field(default=100, ge=0, le=500)
    CRM_BATCH_STOP_ON_MALFORMED_RESPONSE: bool = True
    CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD: bool = True
    CRM_RUNTIME_SKIP_OLDER_PAYLOAD_IF_NEWER_SENT: bool = False

    PARSER_MARK_IGNORED_AS_APPLIED: bool = True
    PARSER_REQUEUE_RETRYABLE_ONCE: bool = True
    PARSER_MAX_EVENT_ATTEMPTS_PER_RUN: int = Field(default=2, ge=1, le=20)

    # --- Parser replay / idempotency / reconciliation (4C) ---
    PARSER_REPLAY_MODE_DEFAULT: str = "snapshot_upsert"
    PARSER_IDEMPOTENCY_SCOPE_DEFAULT: str = "entity_payload"
    PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND: bool = True
    PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS: bool = False
    PARSER_ENABLE_RESPONSE_LOSS_RECONCILIATION: bool = True
    PARSER_ENABLE_RUNTIME_RECONCILIATION: bool = True
    PARSER_ENABLE_CATALOG_FIND_RECONCILIATION: bool = False
    PARSER_RECONCILE_ON_MISSING_IDS: bool = True
    PARSER_RECONCILE_ON_AMBIGUOUS_RESULT: bool = True
    PARSER_RECONCILE_MAX_ATTEMPTS_PER_RUN: int = Field(default=1, ge=0, le=20)
    PARSER_INCLUDE_IDEMPOTENCY_KEY_IN_PAYLOAD: bool = True
    CRM_SEND_IDEMPOTENCY_KEY_HEADER: bool = True

    # --- Active RabbitMQ broker / publisher contour ---
    BROKER_TYPE: str = "rabbitmq"
    RABBITMQ_VHOST: str = "moscraper"
    RABBITMQ_ADMIN_USER: str = "moscraper_admin"
    RABBITMQ_ADMIN_PASS: str = "change-me-admin-pass"
    RABBITMQ_PUBLISHER_USER: str = "moscraper_publisher"
    RABBITMQ_PUBLISHER_PASS: str = "change-me-publisher-pass"
    RABBITMQ_CRM_USER: str = "moscraper_crm"
    RABBITMQ_CRM_PASS: str = "change-me-crm-pass"
    RABBITMQ_URL: str = "amqp://moscraper_publisher:change-me-publisher-pass@localhost:5672/moscraper"
    RABBITMQ_CRM_URL: str = ""
    RABBITMQ_MANAGEMENT_URL: str = "http://127.0.0.1:15672"
    RABBITMQ_EXCHANGE: str = "moscraper.events"
    RABBITMQ_EXCHANGE_TYPE: str = "topic"
    RABBITMQ_QUEUE: str = "scraper.products.v1"
    RABBITMQ_CRM_QUEUE: str = "crm.products.import.v1"
    RABBITMQ_RETRY_EXCHANGE: str = "crm.products.retry"
    RABBITMQ_REQUEUE_EXCHANGE: str = "crm.products.requeue"
    RABBITMQ_DLX_EXCHANGE: str = "crm.products.dlx"
    RABBITMQ_ROUTING_KEY: str = "listing.scraped.v1"
    RABBITMQ_PUBLISH_MANDATORY: bool = True
    RABBITMQ_DECLARE_TOPOLOGY: bool = False
    RABBITMQ_HEARTBEAT_SECONDS: int = Field(default=30, ge=1, le=3600)
    RABBITMQ_CONNECTION_NAME: str = "publisher-service"
    RABBITMQ_RETRY_30S_MS: int = Field(default=30_000, ge=1_000, le=3_600_000)
    RABBITMQ_RETRY_5M_MS: int = Field(default=300_000, ge=1_000, le=7_200_000)
    RABBITMQ_RETRY_30M_MS: int = Field(default=1_800_000, ge=1_000, le=21_600_000)
    RABBITMQ_BOOTSTRAP_RECREATE_MISMATCHED_QUEUES: bool = False
    RABBITMQ_BOOTSTRAP_MANAGE_VHOST: bool = True
    RABBITMQ_BOOTSTRAP_MANAGE_USERS: bool = True
    RABBITMQ_BOOTSTRAP_MANAGE_PERMISSIONS: bool = True
    RABBITMQ_MANAGEMENT_BIND_HOST: str = "127.0.0.1"
    RABBITMQ_AMQP_BIND_HOST: str = "0.0.0.0"
    MAX_PUBLISH_RETRIES: int = Field(default=0, ge=0)

    # --- Scraper DB / outbox / publisher ---
    SCRAPER_DB_BACKEND: str = ""
    SCRAPER_DB_DSN: str = ""
    SCRAPER_DB_MIGRATION_DSN: str = ""
    SCRAPER_DB_PATH: str = "data/scraper/scraper.db"
    SCRAPER_DB_BUSY_TIMEOUT_MS: int = Field(default=5000, ge=100, le=600_000)
    SCRAPER_DB_ENABLE_WAL: bool = True
    SCRAPER_DB_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=50)
    SCRAPER_DB_POOL_MAX_SIZE: int = Field(default=5, ge=1, le=100)
    SCRAPER_OUTBOX_EVENT_TYPE: str = "scraper.product.scraped.v1"
    SCRAPER_OUTBOX_BATCH_SIZE: int = Field(default=50, ge=1, le=500)
    SCRAPER_OUTBOX_LEASE_SECONDS: int = Field(default=60, ge=5, le=3600)
    SCRAPER_OUTBOX_MAX_RETRIES: int = Field(default=8, ge=1, le=100)
    SCRAPER_OUTBOX_RETRY_BASE_SECONDS: int = Field(default=15, ge=1, le=3600)
    PUBLISHER_POLL_INTERVAL_SECONDS: float = Field(default=2.0, ge=0.1, le=60.0)
    PUBLISHER_SERVICE_NAME: str = "publisher-service"

    DEFAULT_CURRENCY: str = "UZS"
    MESSAGE_SCHEMA_VERSION: int = 1

    MOSCRAPER_DISABLE_PUBLISH: bool = False

    PROXY_LIST_PATH: str = ""
    SENTRY_DSN: str = ""

    SCRAPY_LOG_LEVEL: str = "INFO"
    SCRAPY_CONCURRENT_REQUESTS: int = 8
    SCRAPY_DOWNLOAD_DELAY: float = 1.5
    SCRAPY_HEADER_PROFILE_ROTATION_ENABLED: bool = False

    # --- Crawl framework / pagination safety (2A) ---
    SCRAPY_MAX_PAGES_PER_CATEGORY: int = Field(default=200, ge=1)
    SCRAPY_MAX_EMPTY_LISTING_REPEATS: int = Field(default=3, ge=1)
    SCRAPY_MAX_DUPLICATE_LISTING_REPEATS: int = Field(default=2, ge=1)
    SCRAPY_LISTING_SIGNATURE_N: int = Field(default=12, ge=1, le=100)
    SCRAPY_CRAWL_REGISTRY_MAX_ENTRIES: int = Field(default=50_000, ge=0)

    # --- Access layer / anti-bot policy (2B) ---
    SCRAPY_ROTATING_PROXY_ENABLED: bool = False
    SCRAPY_ACCESS_SHELL_ESCALATE_AFTER: int = Field(default=2, ge=1)
    SCRAPY_BROWSER_FALLBACK_FAILURE_THRESHOLD: int = Field(default=2, ge=1)
    SCRAPY_PROXY_FALLBACK_FAILURE_THRESHOLD: int = Field(default=1, ge=1)
    SCRAPY_PROXY_POLICY_HARDENING_ENABLED: bool = False
    SCRAPY_PROXY_POLICY_DEFAULT_MODE: str = "rotating"
    SCRAPY_PROXY_STICKY_REQUESTS_DEFAULT: int = Field(default=20, ge=1, le=1000)
    SCRAPY_PROXY_COOLDOWN_SECONDS_DEFAULT: int = Field(default=300, ge=1, le=86_400)
    SCRAPY_PROXY_BAN_SCORE_THRESHOLD: int = Field(default=3, ge=1, le=100)
    SCRAPY_PROXY_MAX_CONSECUTIVE_FAILURES: int = Field(default=2, ge=1, le=100)
    SCRAPY_CAPTCHA_HOOKS_ENABLED: bool = False
    SCRAPY_CAPTCHA_SOLVER_BACKEND: str = "noop"
    SCRAPY_CAPTCHA_MAX_SOLVE_ATTEMPTS: int = Field(default=1, ge=1, le=20)
    SCRAPY_CAPTCHA_SUSPICIOUS_REDIRECT_ENABLED: bool = True
    SCRAPY_HONEYPOT_FILTER_ENABLED: bool = False
    SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO: float = Field(default=0.8, ge=0.0, le=1.0)
    SCRAPY_BAN_SIGNAL_MONITORING_ENABLED: bool = False
    SCRAPY_BAN_SPIKE_WINDOW_SECONDS: float = Field(default=120.0, ge=1.0, le=3600.0)
    SCRAPY_BAN_SPIKE_THRESHOLD: int = Field(default=5, ge=1, le=1000)
    SCRAPY_RANDOMIZED_DELAY_ENABLED: bool = False
    SCRAPY_RANDOMIZED_DELAY_MIN_SECONDS: float = Field(default=0.05, ge=0.0, le=5.0)
    SCRAPY_RANDOMIZED_DELAY_MAX_SECONDS: float = Field(default=0.35, ge=0.0, le=5.0)
    SCRAPY_EXPLICIT_BACKOFF_ENABLED: bool = False
    SCRAPY_EXPLICIT_BACKOFF_ENFORCE: bool = False
    SCRAPY_EXPLICIT_BACKOFF_ENFORCE_STORES: list[str] = Field(default_factory=list)
    SCRAPY_RATE_LIMIT_HEADER_INTELLIGENCE_ENABLED: bool = True
    SCRAPY_BACKOFF_BASE_SECONDS: float = Field(default=1.0, ge=0.0, le=60.0)
    SCRAPY_BACKOFF_MAX_SECONDS: float = Field(default=90.0, ge=0.0, le=3600.0)
    SCRAPY_BACKOFF_COOLDOWN_MAX_SECONDS: float = Field(default=300.0, ge=0.0, le=86_400.0)
    SCRAPY_BACKOFF_RESPECT_RETRY_AFTER: bool = True
    SCRAPY_BACKOFF_429_STRICT: bool = True

    STORE_NAMES: list[str] = Field(default_factory=lambda: ["mediapark", "texnomart", "uzum", "alifshop"])

    # --- Spec extraction governance (3B) ---
    ENABLE_STORE_SPEC_OVERRIDES: bool = True
    ENABLE_DEPRECATED_ALIAS_WARNINGS: bool = True
    ENABLE_SPEC_COVERAGE_REPORT: bool = True
    SPEC_MAPPING_MIN_COVERAGE_WARNING: float = Field(default=0.35, ge=0.0, le=1.0)
    CRM_INCLUDE_SPEC_COVERAGE: bool = True

    # --- Typed spec confidence & suppression (3C) ---
    ENABLE_TYPED_SPEC_CONFIDENCE: bool = True
    ENABLE_TYPED_SPEC_SUPPRESSION: bool = True
    TYPED_SPEC_MIN_CONFIDENCE_DEFAULT: float = Field(default=0.65, ge=0.0, le=1.0)
    TYPED_SPEC_MIN_CONFIDENCE_PHONE: float = Field(default=0.70, ge=0.0, le=1.0)
    TYPED_SPEC_MIN_CONFIDENCE_LAPTOP: float = Field(default=0.70, ge=0.0, le=1.0)
    TYPED_SPEC_MIN_CONFIDENCE_TV: float = Field(default=0.60, ge=0.0, le=1.0)
    TYPED_SPEC_MIN_CONFIDENCE_TABLET: float = Field(default=0.70, ge=0.0, le=1.0)
    TYPED_SPEC_MIN_CONFIDENCE_APPLIANCE: float = Field(default=0.60, ge=0.0, le=1.0)
    ENABLE_NORMALIZATION_QUALITY_SUMMARY: bool = True

    CRM_INCLUDE_FIELD_CONFIDENCE: bool = True
    CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS: bool = True
    CRM_INCLUDE_NORMALIZATION_QUALITY: bool = True

    # --- Parser observability / ETL diagnostics (5A) ---
    ENABLE_STRUCTURED_SYNC_LOGS: bool = True
    ENABLE_IN_MEMORY_TRACE_BUFFER: bool = True
    TRACE_BUFFER_MAX_RECORDS: int = Field(default=5000, ge=100, le=200_000)
    ENABLE_BATCH_TRACE: bool = True
    ENABLE_HEALTH_SNAPSHOT: bool = True
    HEALTH_SNAPSHOT_INTERVAL_SECONDS: int = Field(default=60, ge=1, le=3600)
    ENABLE_FAILURE_CLASSIFICATION: bool = True
    ENABLE_SYNC_CORRELATION_IDS: bool = True
    ENABLE_DIAGNOSTIC_PAYLOAD_SUMMARY: bool = True
    ENABLE_ETL_STATUS_EXPORT: bool = True

    # --- Parser SLO / operational policy (5B) ---
    SLO_MIN_PARSE_SUCCESS_RATE: float = Field(default=0.90, ge=0.0, le=1.0)
    SLO_MIN_APPLY_SUCCESS_RATE: float = Field(default=0.95, ge=0.0, le=1.0)
    SLO_MAX_BLOCK_PAGE_RATE: float = Field(default=0.10, ge=0.0, le=1.0)
    SLO_MAX_ZERO_RESULT_CATEGORY_RATE: float = Field(default=0.20, ge=0.0, le=1.0)
    SLO_MAX_LOW_COVERAGE_RATE: float = Field(default=0.35, ge=0.0, le=1.0)
    SLO_MAX_REJECTED_ITEM_RATE: float = Field(default=0.15, ge=0.0, le=1.0)
    SLO_MAX_RETRYABLE_FAILURE_RATE: float = Field(default=0.10, ge=0.0, le=1.0)
    SLO_MAX_MALFORMED_RESPONSE_RATE: float = Field(default=0.05, ge=0.0, le=1.0)

    SLO_MAX_UNRESOLVED_RECONCILIATION_RATE: float = Field(default=0.05, ge=0.0, le=1.0)
    SLO_MAX_DUPLICATE_PAYLOAD_SKIP_RATE: float = Field(default=0.50, ge=0.0, le=1.0)
    SLO_MIN_ITEMS_PER_ACTIVE_STORE: int = Field(default=20, ge=0, le=1_000_000)
    INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT: bool = False
    INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT: bool = False
    ENABLE_OPERATIONAL_POLICY_LOGS: bool = True

    # --- Operator support / triage / runbooks (5C) ---
    ENABLE_OPERATOR_TRIAGE_SUMMARY: bool = True
    ENABLE_RUNBOOK_GENERATION: bool = True
    ENABLE_SAFE_REPLAY_SUPPORT: bool = True
    ENABLE_DIAGNOSTIC_SNAPSHOTS: bool = True
    ENABLE_STORE_DISABLE_ADVICE: bool = True
    SAFE_REPLAY_ALLOW_PRODUCT_FOUND: bool = True
    SAFE_REPLAY_ALLOW_DELTA_EVENTS: bool = False
    SAFE_REPLAY_MAX_ITEMS_PER_ACTION: int = Field(
        default=20,
        ge=1,
        le=10_000,
        validation_alias=AliasChoices("SAFE_REPLAY_MAX_ITEMS_PER_ACTION", "SAFE_REPLAY_MAX_ITEMS"),
    )
    SAFE_REPLAY_MAX_BATCHES_PER_ACTION: int = Field(
        default=3,
        ge=0,
        le=100,
        validation_alias=AliasChoices("SAFE_REPLAY_MAX_BATCHES_PER_ACTION", "SAFE_REPLAY_MAX_BATCHES"),
    )
    SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY: bool = True
    DIAGNOSTIC_ERROR_SAMPLE_SIZE: int = Field(default=20, ge=1, le=200)

    # --- Rollout / feature flags (6B): progressive enablement, no external SaaS ---
    ENABLE_FEATURE_FLAGS: bool = True
    ENABLE_STORE_ROLLOUT_POLICY: bool = True
    ENABLE_CANARY_ROLLOUT: bool = True
    ENABLE_PROGRESSIVE_STORE_ENABLEMENT: bool = True
    ROLLOUT_DEFAULT_STAGE: str = "disabled"
    ROLLOUT_CANARY_PERCENTAGE: int = Field(default=10, ge=0, le=100)
    ROLLOUT_PARTIAL_PERCENTAGE: int = Field(default=30, ge=0, le=100)
    ROLLOUT_HASH_BASED_SELECTION: bool = True
    ENABLE_AUTO_ROLLBACK_ADVICE: bool = True
    ENABLE_ROLLOUT_GUARD_BY_STATUS: bool = True
    ROLLOUT_BLOCK_ON_FAILING_STATUS: bool = True
    ROLLOUT_ALLOW_DEGRADED_CANARY: bool = False
    ROLLOUT_DISABLED_STORES: list[str] = Field(default_factory=list)
    ROLLOUT_CANARY_STORES: list[str] = Field(default_factory=list)
    ROLLOUT_PARTIAL_STORES: list[str] = Field(default_factory=list)

    # --- Release quality logs (6A): off by default to keep unit tests quiet ---
    ENABLE_RELEASE_QUALITY_LOGS: bool = False

    # --- Contract evolution / parser→CRM compatibility (6C) ---
    CONTRACT_SCHEMA_VERSION: str = "v1"
    ENABLE_DUAL_SHAPE_OUTPUTS: bool = False
    ENABLE_SHADOW_FIELDS: bool = True
    ENABLE_DEPRECATION_WARNINGS: bool = True
    ENABLE_MIGRATION_READINESS_REPORT: bool = True
    ALLOW_BREAKING_CHANGES_WITHOUT_GATE: bool = False
    DEFAULT_DEPRECATION_STAGE: str = "deprecated"
    ENABLE_COMPATIBILITY_GUARDS: bool = True

    # --- Security baseline / secrets / request integrity (7A) ---
    SECURITY_MODE: str = "baseline"
    CRM_PARSER_KEY_FILE: str = ""
    ENABLE_SECRET_FILE_FALLBACK: bool = True
    ENABLE_SECRET_REDACTION: bool = True
    ENABLE_SECURITY_STARTUP_VALIDATION: bool = True
    CRM_REQUEST_INTEGRITY_MODE: str = "none"
    CRM_REQUEST_SIGNING_SECRET: str = ""
    CRM_REQUEST_SIGNING_SECRET_FILE: str = ""
    CRM_REQUEST_TIMESTAMP_HEADER: str = "X-Request-Timestamp"
    CRM_REQUEST_NONCE_HEADER: str = "X-Request-Nonce"
    CRM_REQUEST_SIGNATURE_HEADER: str = "X-Request-Signature"
    CRM_REQUEST_SIGNATURE_ALGORITHM: str = "hmac-sha256"
    MASK_SENSITIVE_HEADERS_IN_LOGS: bool = True
    MASK_SENSITIVE_FIELDS_IN_LOGS: bool = True
    SECURITY_FAIL_FAST_ON_INVALID_CONFIG: bool = True

    # --- Network safety / outbound controls (7B) ---
    NETWORK_SECURITY_MODE: str = "restricted"
    ENABLE_OUTBOUND_HOST_ALLOWLIST: bool = True
    ENABLE_PRIVATE_IP_BLOCK: bool = True
    ENABLE_LOCALHOST_BLOCK: bool = True
    ENABLE_FILE_SCHEME_BLOCK: bool = True
    ENABLE_UNSAFE_SCHEME_BLOCK: bool = True
    ENABLE_REDIRECT_HOST_VALIDATION: bool = True
    MAX_REDIRECT_HOPS: int = Field(default=5, ge=0, le=50)
    ENABLE_BROWSER_SAME_ORIGIN_GUARD: bool = True
    ENABLE_PROXY_HOST_VALIDATION: bool = True
    ENABLE_STORE_HOST_PINNING: bool = True
    ENABLE_CRM_HOST_PINNING: bool = True
    ALLOWED_STORE_HOSTS: list[str] = Field(
        default_factory=lambda: [
            "mediapark.uz",
            "www.mediapark.uz",
            "uzum.uz",
            "www.uzum.uz",
            "texnomart.uz",
            "www.texnomart.uz",
            "alifshop.uz",
            "www.alifshop.uz",
        ]
    )
    ALLOWED_CRM_HOSTS: list[str] = Field(default_factory=list)
    ALLOWED_PROXY_HOSTS: list[str] = Field(default_factory=list)
    BLOCK_PRIVATE_NETWORK_RANGES: bool = True
    BLOCK_METADATA_IPS: bool = True

    # --- Data minimization / operational hygiene (7C) ---
    ENABLE_DATA_MINIMIZATION: bool = True
    ENABLE_RUNTIME_RETENTION_LIMITS: bool = True
    ENABLE_SAFE_DIAGNOSTIC_EXPORTS: bool = True
    ENABLE_REPLAY_ABUSE_GUARDS: bool = True
    ENABLE_SUPPORT_SCOPE_RESTRICTIONS: bool = True
    TRACE_MAX_AGE_SECONDS: int = Field(default=3600, ge=0, le=864_000)
    BATCH_TRACE_MAX_AGE_SECONDS: int = Field(default=3600, ge=0, le=864_000)
    DIAGNOSTIC_SNAPSHOT_MAX_ITEMS: int = Field(default=20, ge=1, le=500)
    SUPPORT_EXPORT_MAX_ERRORS: int = Field(default=20, ge=0, le=500)
    SUPPORT_EXPORT_INCLUDE_RAW_SPECS: bool = True
    SUPPORT_EXPORT_INCLUDE_TYPED_SPECS: bool = True
    SUPPORT_EXPORT_INCLUDE_FIELD_CONFIDENCE: bool = False
    SUPPORT_EXPORT_INCLUDE_SUPPRESSED_FIELDS: bool = False
    SUPPORT_EXPORT_INCLUDE_RAW_HEADERS: bool = False
    SUPPORT_EXPORT_INCLUDE_FULL_URL_QUERY: bool = False

    # --- Performance profiling / baseline (8A) ---
    ENABLE_PERFORMANCE_PROFILING: bool = True
    ENABLE_STAGE_TIMING: bool = True
    ENABLE_STORE_PERFORMANCE_SNAPSHOT: bool = True
    ENABLE_RUN_PERFORMANCE_SNAPSHOT: bool = True
    ENABLE_BOTTLENECK_DETECTION: bool = True
    STAGE_TIMING_BUFFER_MAX_RECORDS: int = Field(default=10_000, ge=10, le=1_000_000)
    PERFORMANCE_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)
    PERF_SLOW_REQUEST_MS: int = Field(default=3000, ge=1)
    PERF_SLOW_PRODUCT_PARSE_MS: int = Field(default=1000, ge=1)
    PERF_SLOW_NORMALIZE_MS: int = Field(default=500, ge=1)
    PERF_SLOW_CRM_SEND_MS: int = Field(default=2000, ge=1)
    PERF_SLOW_BATCH_APPLY_MS: int = Field(default=3000, ge=1)
    PERF_CRITICAL_MEMORY_MB: int = Field(default=512, ge=1)
    PERF_SNAPSHOT_INTERVAL_SECONDS: int = Field(default=60, ge=1, le=3600)

    # --- Resource governance / scaling (8B) ---
    ENABLE_RESOURCE_GOVERNANCE: bool = True
    ENABLE_STORE_RESOURCE_BUDGETS: bool = True
    ENABLE_BACKPRESSURE_POLICY: bool = True
    ENABLE_BATCH_BACKPRESSURE: bool = True
    ENABLE_BROWSER_BUDGETS: bool = True
    ENABLE_PROXY_BUDGETS: bool = True
    ENABLE_MEMORY_GUARD: bool = True
    GLOBAL_MAX_CONCURRENT_REQUESTS: int = Field(default=16, ge=1, le=256)
    GLOBAL_MAX_INFLIGHT_BATCHES: int = Field(default=4, ge=1, le=64)
    GLOBAL_MAX_BROWSER_PAGES: int = Field(default=2, ge=0, le=64)
    GLOBAL_MAX_PROXY_REQUESTS: int = Field(default=8, ge=0, le=256)
    GLOBAL_MAX_RETRYABLE_QUEUE: int = Field(default=200, ge=0, le=50_000)
    GLOBAL_MAX_MEMORY_MB: int = Field(default=512, ge=1, le=65_536)
    SCRAPY_RESOURCE_GOV_BYPASS_STORES: list[str] = Field(default_factory=list)
    BACKPRESSURE_MEMORY_WARNING_MB: int = Field(default=384, ge=1, le=65_536)
    BACKPRESSURE_MEMORY_CRITICAL_MB: int = Field(default=512, ge=1, le=65_536)
    BACKPRESSURE_RETRYABLE_QUEUE_WARNING: int = Field(default=100, ge=0, le=50_000)
    BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL: int = Field(default=200, ge=0, le=50_000)
    BACKPRESSURE_BATCH_INFLIGHT_WARNING: int = Field(default=3, ge=0, le=64)
    BACKPRESSURE_BATCH_INFLIGHT_CRITICAL: int = Field(default=4, ge=0, le=64)

    # --- Cost / efficiency / regression gates (8C) ---
    ENABLE_COST_EFFICIENCY_TRACKING: bool = True
    ENABLE_COST_REGRESSION_GATES: bool = True
    COST_WEIGHT_HTTP_REQUEST: float = Field(default=1.0, ge=0.0)
    COST_WEIGHT_PROXY_REQUEST: float = Field(default=2.0, ge=0.0)
    COST_WEIGHT_BROWSER_PAGE: float = Field(default=5.0, ge=0.0)
    COST_WEIGHT_RETRY_ATTEMPT: float = Field(default=1.5, ge=0.0)
    COST_WEIGHT_BATCH_FLUSH: float = Field(default=0.5, ge=0.0)
    COST_WEIGHT_CRM_ROUNDTRIP: float = Field(default=1.0, ge=0.0)
    COST_WEIGHT_NORMALIZATION_UNIT: float = Field(default=0.5, ge=0.0)
    COST_WEIGHT_DIAGNOSTIC_UNIT: float = Field(default=0.2, ge=0.0)
    EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT: float = Field(default=0.5, ge=0.0)
    EFFICIENCY_MIN_APPLIED_PER_COST_UNIT: float = Field(default=0.4, ge=0.0)
    EFFICIENCY_MAX_BROWSER_SHARE: float = Field(default=0.30, ge=0.0, le=1.0)
    EFFICIENCY_MAX_RETRY_SHARE: float = Field(default=0.20, ge=0.0, le=1.0)
    EFFICIENCY_MAX_PROXY_SHARE: float = Field(default=0.40, ge=0.0, le=1.0)
    PERF_REGRESSION_MAX_REQUEST_MS_DELTA_PCT: float = Field(default=25.0, ge=0.0, le=500.0)
    PERF_REGRESSION_MAX_NORMALIZE_MS_DELTA_PCT: float = Field(default=25.0, ge=0.0, le=500.0)
    PERF_REGRESSION_MAX_CRM_SEND_MS_DELTA_PCT: float = Field(default=25.0, ge=0.0, le=500.0)
    PERF_REGRESSION_MAX_COST_PER_PRODUCT_DELTA_PCT: float = Field(default=30.0, ge=0.0, le=500.0)

    # --- Developer experience / local DX (9B) ---
    DEV_MODE: bool = False
    DEV_RUN_MODE: str = "normal"
    DEV_DRY_RUN_DISABLE_CRM_SEND: bool = True
    DEV_ENABLE_DEBUG_SUMMARIES: bool = True
    DEV_ENABLE_SINGLE_STORE_MODE: bool = True
    DEV_ENABLE_FIXTURE_REPLAY: bool = True
    DEV_ENABLE_VERBOSE_STAGE_OUTPUT: bool = False
    DEV_DEBUG_MAX_ITEMS: int = Field(default=20, ge=1, le=5000)
    DEV_DEBUG_INCLUDE_RAW_SPECS: bool = True
    DEV_DEBUG_INCLUDE_TYPED_SPECS: bool = True
    DEV_DEBUG_INCLUDE_LIFECYCLE: bool = True
    DEV_DEBUG_INCLUDE_APPLY_RESULTS: bool = True

    # --- Go-live / cutover / stabilization (10C) ---
    ENABLE_GO_LIVE_POLICY: bool = True
    ENABLE_CUTOVER_CHECKLIST: bool = True
    ENABLE_STABILIZATION_CHECKPOINTS: bool = True
    ENABLE_ROLLBACK_TRIGGER_EVALUATION: bool = True
    GO_LIVE_REQUIRE_READINESS_READY: bool = True
    GO_LIVE_REQUIRE_RELEASE_GATES_PASS: bool = True
    GO_LIVE_REQUIRE_SECURITY_BASELINE: bool = True
    GO_LIVE_REQUIRE_ENABLED_STORE_PLAYBOOKS: bool = True
    GO_LIVE_REQUIRE_OBSERVABILITY_BASELINE: bool = True
    GO_LIVE_REQUIRE_ROLLOUT_POLICY: bool = True
    GO_LIVE_CANARY_ONLY_FIRST: bool = True
    STABILIZATION_BLOCK_ON_CRITICAL_ALERTS: bool = True
    STABILIZATION_MAX_CRITICAL_ALERTS: int = Field(default=0, ge=0, le=100)
    STABILIZATION_MAX_HIGH_ALERTS: int = Field(default=3, ge=0, le=1000)
    STABILIZATION_MAX_REJECTED_ITEM_RATE: float = Field(default=0.15, ge=0.0, le=1.0)
    STABILIZATION_MAX_BLOCK_PAGE_RATE: float = Field(default=0.10, ge=0.0, le=1.0)
    STABILIZATION_MAX_MALFORMED_RESPONSE_RATE: float = Field(default=0.05, ge=0.0, le=1.0)
    STABILIZATION_MAX_UNRESOLVED_RECONCILIATION_RATE: float = Field(default=0.05, ge=0.0, le=1.0)

    def resolved_rabbitmq_crm_url(self) -> str:
        if self.RABBITMQ_CRM_URL:
            return self.RABBITMQ_CRM_URL
        return _replace_rabbitmq_url_credentials(
            self.RABBITMQ_URL,
            username=self.RABBITMQ_CRM_USER,
            password=self.RABBITMQ_CRM_PASS,
        )

    def resolved_scraper_db_backend(self) -> str:
        configured = (self.SCRAPER_DB_BACKEND or "").strip().lower()
        if configured:
            return configured
        if self.SCRAPER_DB_DSN:
            return "postgres"
        return "sqlite"


settings = Settings()
