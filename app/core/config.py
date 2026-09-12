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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
