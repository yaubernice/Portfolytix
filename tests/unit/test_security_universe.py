from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.models import Security
from app.repositories.security_repository import SecurityQuery, SecurityRepository


def _listing(
    session: Session,
    *,
    ticker: str,
    name: str,
    exchange: str = "NASDAQ",
    provider: str = "seed",
    provider_symbol: str | None = None,
    sector: str = "Technology",
    country: str = "US",
    asset_type: str = "equity",
) -> Security:
    row = Security(
        ticker=ticker,
        name=name,
        exchange=exchange,
        sector=sector,
        country=country,
        currency="USD",
        asset_type=asset_type,
        provider=provider,
        provider_symbol=provider_symbol or ticker,
    )
    session.add(row)
    session.flush()
    return row


def test_same_ticker_can_exist_for_two_providers(sqlite_session: Session) -> None:
    first = _listing(
        sqlite_session,
        ticker="AAPL",
        name="Apple Inc.",
        provider="seed",
        provider_symbol="AAPL",
    )
    second = _listing(
        sqlite_session,
        ticker="AAPL",
        name="Apple Inc.",
        exchange="LSE",
        provider="other",
        provider_symbol="AAPL.L",
        country="GB",
    )
    assert first.id != second.id
    with pytest.raises(ConflictError):
        SecurityRepository(sqlite_session).get_by_ticker("AAPL")


def test_duplicate_provider_symbol_is_rejected(sqlite_session: Session) -> None:
    _listing(sqlite_session, ticker="MSFT", name="Microsoft", provider_symbol="MSFT")
    with pytest.raises(IntegrityError):
        _listing(
            sqlite_session,
            ticker="MSFT",
            name="Microsoft again",
            provider_symbol="MSFT",
        )


def test_search_filters_and_paginates(sqlite_session: Session) -> None:
    _listing(sqlite_session, ticker="AAPL", name="Apple Inc.", sector="Technology")
    _listing(
        sqlite_session,
        ticker="JPM",
        name="JPMorgan Chase",
        exchange="NYSE",
        sector="Financials",
        provider_symbol="JPM",
    )
    _listing(
        sqlite_session,
        ticker="VOD",
        name="Vodafone",
        exchange="LSE",
        sector="Communication Services",
        country="GB",
        asset_type="equity",
        provider_symbol="VOD.L",
    )
    repo = SecurityRepository(sqlite_session)
    rows, total = repo.search(SecurityQuery(q="app", limit=20, offset=0))
    assert total == 1
    assert rows[0].ticker == "AAPL"
    rows, total = repo.search(
        SecurityQuery(exchange="lse", country="gb", limit=20, offset=0)
    )
    assert total == 1
    assert rows[0].ticker == "VOD"
    page, total = repo.search(SecurityQuery(sector="technology", limit=1, offset=0))
    assert total == 1
    assert len(page) == 1
    missing, total = repo.search(SecurityQuery(asset_type="etf", limit=20, offset=0))
    assert total == 0
    assert missing == []
    assert repo.get_by_id(uuid4()) is None
