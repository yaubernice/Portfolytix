import os
from collections.abc import Iterator

# Must run before any import of app.core.config / app.main so TestClient
# lifespan does not start APScheduler or call a live vendor.
os.environ["SCHEDULER_ENABLED"] = "false"
# Unit/API tests use an explicit in-memory fake when they test caching.
os.environ["CACHE_ENABLED"] = "false"
# Phase 12 tests must not call a live language-model API.
os.environ["AI_PROVIDER"] = "local"
# Quote tests use an in-memory store. The worker is a separate process.
os.environ["QUOTE_PROVIDER"] = "simulator"
# News tests stay on the cache. A local .env must not call a headline vendor.
os.environ["NEWS_PROVIDER"] = ""
# Suggestion tests keep stored figures. A local .env must not call Yahoo.
os.environ["IDEAS_LIVE_QUOTES"] = "false"
# Position and trade tests keep the price in the request. A local .env must
# not replace it with a vendor quote.
os.environ["PROVIDER_MARKS"] = "false"
# Analytics tests keep the bars they insert. A local .env must not call Yahoo.
os.environ["PORTFOLIO_HISTORY_BACKFILL"] = "false"

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def sqlite_session(sqlite_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def postgres_is_reachable() -> bool:
    from sqlalchemy.exc import OperationalError

    from app.core.config import settings

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False
    finally:
        engine.dispose()
