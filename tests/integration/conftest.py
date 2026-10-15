from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.conftest import postgres_is_reachable


@pytest.fixture(scope="session")
def postgres_engine():
    if not postgres_is_reachable():
        pytest.skip("PostgreSQL is not reachable (start the stack with make up)")

    # Same migration path as production. create_all() is not used here.
    command.upgrade(Config("alembic.ini"), "head")

    from app.core.config import settings

    engine = create_engine(settings.database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def postgres_session(postgres_engine) -> Iterator[Session]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    # commit() inside a service releases a savepoint. The connection
    # transaction below still rolls back, so tests do not keep rows.
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
