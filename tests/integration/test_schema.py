import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from tests.conftest import postgres_is_reachable

pytestmark = pytest.mark.skipif(
    not postgres_is_reachable(),
    reason="PostgreSQL is not reachable (start the stack with make up)",
)


def test_alembic_upgrade_creates_phase2_tables() -> None:
    from app.core.config import settings

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(settings.database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "users",
            "portfolios",
            "securities",
            "prices",
            "transactions",
            "job_runs",
            "fundamentals",
        }.issubset(tables)

        price_indexes = {
            index["name"]: index for index in inspector.get_indexes("prices")
        }
        price_history_index = price_indexes["uq_prices_security_id_timestamp"]
        assert price_history_index["unique"] is True
        assert tuple(price_history_index["column_names"]) == (
            "security_id",
            "timestamp",
        )

        index_names = {index["name"] for index in inspector.get_indexes("transactions")}
        assert "ix_transactions_portfolio_id_timestamp" in index_names
        assert "ix_transactions_portfolio_id_security_id" in index_names

        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM securities LIMIT 1"))
    finally:
        engine.dispose()
