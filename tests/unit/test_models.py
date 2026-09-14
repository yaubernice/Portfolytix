from sqlalchemy import CheckConstraint, Float, Numeric, UniqueConstraint

from app.db.base import Base
from app.db.models import Portfolio, Price, Security, Transaction, User


def test_no_holdings_table() -> None:
    """Holdings are derived from transactions; they are not a stored table."""
    assert "holdings" not in Base.metadata.tables


def test_expected_tables_exist() -> None:
    assert {User.__tablename__, Portfolio.__tablename__} <= set(Base.metadata.tables)
    assert set(Base.metadata.tables) == {
        "users",
        "portfolios",
        "securities",
        "prices",
        "transactions",
    }


def test_price_and_quantity_columns_are_numeric_not_float() -> None:
    for column_name in ("open", "high", "low", "close", "adjusted_close"):
        column = Price.__table__.c[column_name]
        assert isinstance(column.type, Numeric)
        assert not isinstance(column.type, Float)
        assert column.type.asdecimal is True

    assert isinstance(Transaction.__table__.c["quantity"].type, Numeric)
    assert isinstance(Transaction.__table__.c["price"].type, Numeric)
    assert not isinstance(Transaction.__table__.c["quantity"].type, Float)


def test_prices_have_composite_unique_on_security_and_timestamp() -> None:
    uniques = [
        constraint
        for constraint in Price.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    column_sets = [
        tuple(col.name for col in constraint.columns) for constraint in uniques
    ]
    assert ("security_id", "timestamp") in column_sets


def test_portfolio_and_transaction_indexes() -> None:
    portfolio_indexes = Base.metadata.tables["portfolios"].indexes
    portfolio_index_names = {index.name for index in portfolio_indexes}
    assert "ix_portfolios_user_id" in portfolio_index_names

    transaction_indexes = {
        index.name: tuple(col.name for col in index.columns)
        for index in Base.metadata.tables["transactions"].indexes
    }
    assert transaction_indexes["ix_transactions_portfolio_id_timestamp"] == (
        "portfolio_id",
        "timestamp",
    )
    assert transaction_indexes["ix_transactions_portfolio_id_security_id"] == (
        "portfolio_id",
        "security_id",
    )


def test_ticker_is_unique() -> None:
    assert Security.__table__.c["ticker"].unique is True


def test_check_constraint_names() -> None:
    price_checks = {
        constraint.name
        for constraint in Price.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_prices_high_gte_low" in price_checks
    assert "ck_prices_positive" in price_checks

    txn_checks = {
        constraint.name
        for constraint in Transaction.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_transactions_type" in txn_checks
    assert "ck_transactions_quantity_positive" in txn_checks
