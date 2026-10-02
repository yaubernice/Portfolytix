from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables (and optional `.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FinSight"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://finsight:finsight@localhost:15432/finsight"
    )
    # Annual decimal, e.g. 0.05 = 5%. Used only for Sharpe. Not a forecast.
    risk_free_rate: Decimal = Decimal("0.05")
    trading_days_per_year: int = 252
    # Market-data pipeline. Never commit a real API key.
    market_data_provider: str = "stooq"
    market_data_api_key: str = ""
    # Background jobs. Tests set SCHEDULER_ENABLED=false so TestClient
    # does not start APScheduler or call a live vendor.
    scheduler_enabled: bool = True
    # 22:00 UTC is after the US cash close in both EST and EDT.
    market_data_cron: str = "0 22 * * *"
    market_data_lookback_days: int = 7
    job_stale_after_seconds: int = 3600
    # Redis is an acceleration layer only. PostgreSQL remains authoritative.
    cache_enabled: bool = True
    redis_url: str = "redis://localhost:16379/0"
    cache_key_prefix: str = "finsight"
    analytics_cache_ttl_seconds: int = 300
    screening_cache_ttl_seconds: int = 300
    redis_socket_timeout_seconds: float = 0.2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
