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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
