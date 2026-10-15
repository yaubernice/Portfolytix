from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Runtime settings come from environment variables and optional .env.
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
    # One run cannot walk the whole universe or a multi-decade window.
    market_data_max_securities: int = 25
    market_data_max_window_days: int = 1825
    market_data_max_attempts: int = 3
    market_data_retry_backoff_seconds: float = 0.0
    market_data_pause_seconds: float = 0.0
    # Alpha Vantage "full" is the entire daily history. Compact is enough
    # unless an older window is explicitly allowed.
    market_data_allow_full_history: bool = False
    job_stale_after_seconds: int = 3600
    # Redis is an acceleration layer only. PostgreSQL remains authoritative.
    cache_enabled: bool = True #enable caching to speed up the application
    redis_url: str = "redis://localhost:16379/0" #Redis URL for the cache
    cache_key_prefix: str = "finsight" #prefix for the cache keys
    analytics_cache_ttl_seconds: int = 300 #time to live for the analytics cache
    screening_cache_ttl_seconds: int = 300 #time to live for the screening cache
    redis_socket_timeout_seconds: float = 0.2 #timeout for the Redis connection
    # Phase 10 authentication. Override the development secret outside local.
    jwt_secret_key: str = "dev-only-change-this-secret-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "finsight"
    jwt_access_token_minutes: int = 30
    # Phase 12. local uses rules and a template. openai defaults to Responses.
    # The model never receives a database connection.
    ai_provider: str = "local"
    ai_openai_api: str = "responses"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 20.0
    # If the remote model is unavailable, retain an evidence-only local answer.
    ai_fallback_to_local: bool = True
    # Live quotes are current state in Redis. Daily bars stay in PostgreSQL.
    # simulator needs no key. finnhub streams trades. alpha_vantage polls
    # GLOBAL_QUOTE (delayed unless the key has a realtime entitlement).
    quote_provider: str = "simulator"
    quote_symbols: str = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA"
    quote_poll_seconds: float = 2.0
    quote_ttl_seconds: int = 30
    # A provider tick older than this can no longer be presented as real-time.
    quote_stale_after_seconds: float = 15.0
    # Delayed quotes go stale when FinSight has not refreshed them. The
    # vendor print can be the previous session without being a failure.
    quote_delayed_stale_after_seconds: float = 120.0
    # Daily bars older than this many sessions are stale. Weekends and
    # NYSE holidays are not sessions.
    history_stale_after_business_days: int = 3
    quote_worker_heartbeat_ttl_seconds: int = 30
    # Watchlist names above this count are not subscribed in one worker pass.
    quote_max_symbols: int = 50
    quote_reconnect_seconds: float = 2.0
    quote_symbol_refresh_seconds: float = 30.0
    # GLOBAL_QUOTE stays delayed unless the key's entitlement is real-time.
    alpha_vantage_realtime: bool = False
    # Empty follows the quote provider. yahoo needs no key. none stores none.
    news_provider: str = ""
    finnhub_api_key: str = ""
    news_ttl_seconds: int = 900
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"


@lru_cache
def get_settings() -> Settings: #dependency function to get the settings
    return Settings()


settings = get_settings()
