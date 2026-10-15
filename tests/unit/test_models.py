from sqlalchemy import CheckConstraint, Float, Numeric, UniqueConstraint

from app.db.base import Base
from app.db.models import Fundamental, Portfolio, Price, Security, Transaction, User


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
        "job_runs",
        "fundamentals",
            "watchlists",
            "watchlist_items",
            "research_flags",
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

    for column_name in (
        "roe",
        "pe_ratio",
        "revenue_growth",
        "market_cap",
        "eps",
        "revenue",
        "profit_margin",
        "dividend_yield",
        "beta",
        "ebitda",
        "shares_outstanding",
        "price_to_book",
        "price_to_sales",
        "roa",
        "earnings_growth",
    ):
        column = Fundamental.__table__.c[column_name]
        assert isinstance(column.type, Numeric)
        assert not isinstance(column.type, Float)


def test_prices_have_covering_unique_index() -> None:
    index = next(
        item
        for item in Price.__table__.indexes
        if item.name == "uq_prices_security_id_timestamp"
    )
    assert index.unique is True
    assert tuple(column.name for column in index.columns) == (
        "security_id",
        "timestamp",
    )
    assert index.dialect_options["postgresql"]["include"] == ["adjusted_close"]


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

    job_indexes = {
        index.name: tuple(col.name for col in index.columns)
        for index in Base.metadata.tables["job_runs"].indexes
    }
    assert job_indexes["ix_job_runs_job_name_started_at"] == (
        "job_name",
        "started_at",
    )
    assert "uq_job_runs_running_job_name" in job_indexes

    fundamental_uniques = [
        tuple(col.name for col in constraint.columns)
        for constraint in Fundamental.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert ("security_id",) in fundamental_uniques


def test_provider_symbol_is_the_security_identity() -> None:
    assert Security.__table__.c["ticker"].unique is not True
    uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in Security.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("provider", "provider_symbol") in uniques
    index_names = {index.name for index in Security.__table__.indexes}
    assert "ix_securities_ticker" in index_names


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

    fund_checks = {
        constraint.name
        for constraint in Fundamental.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_fundamentals_market_cap_positive" in fund_checks
