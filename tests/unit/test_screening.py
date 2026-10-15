from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models import Fundamental, Security
from app.schemas.screening import ScreenRequest
from app.services.screening_service import ScreeningService
from tests.fakes import FakeCache


def _security(
    session: Session,
    ticker: str,
    *,
    sector: str = "Technology",
    industry: str | None = None,
    exchange: str = "NASDAQ",
) -> Security:
    row = Security(
        ticker=ticker,
        name=f"{ticker} Inc.",
        exchange=exchange,
        sector=sector,
        industry=industry,
        currency="USD",
    )
    session.add(row)
    session.flush()
    return row


def _fundamentals(
    session: Session,
    security: Security,
    *,
    roe: str,
    pe: str,
    growth: str,
    mcap: str,
) -> Fundamental:
    row = Fundamental(
        security_id=security.id,
        as_of=date(2025, 12, 31),
        roe=Decimal(roe),
        pe_ratio=Decimal(pe),
        revenue_growth=Decimal(growth),
        market_cap=Decimal(mcap),
    )
    session.add(row)
    session.flush()
    return row


def _seed_seven(session: Session) -> None:
    specs = (
        ("AAPL", "Technology", "0.35", "28", "0.08", "3500000000000"),
        ("MSFT", "Technology", "0.38", "32", "0.14", "3100000000000"),
        ("NVDA", "Technology", "0.70", "45", "0.80", "2200000000000"),
        ("AMZN", "Consumer Discretionary", "0.18", "35", "0.11", "1800000000000"),
        ("GOOGL", "Communication Services", "0.28", "22", "0.12", "2000000000000"),
        ("META", "Communication Services", "0.32", "24", "0.16", "1200000000000"),
        ("TSLA", "Consumer Discretionary", "0.12", "55", "0.05", "700000000000"),
    )
    for ticker, sector, roe, pe, growth, mcap in specs:
        security = _security(session, ticker, sector=sector)
        _fundamentals(
            session, security, roe=roe, pe=pe, growth=growth, mcap=mcap
        )


def test_dividend_filter_skips_a_null_yield(sqlite_session: Session) -> None:
    apple = _security(sqlite_session, "AAPL")
    meta = _security(sqlite_session, "META")
    _fundamentals(
        sqlite_session, apple, roe="0.35", pe="28", growth="0.08", mcap="100"
    )
    paying = _fundamentals(
        sqlite_session, meta, roe="0.32", pe="24", growth="0.16", mcap="100"
    )
    paying.dividend_yield = Decimal("0.02")
    sqlite_session.flush()
    result = ScreeningService(sqlite_session).screen(
        ScreenRequest(dividend_yield_min=Decimal("0.01"))
    )
    assert [hit.ticker for hit in result.items] == ["META"]
    assert result.applied.dividend_yield_min == Decimal("0.01")


def test_example_screen_returns_googl_and_meta(sqlite_session: Session) -> None:
    _seed_seven(sqlite_session)
    result = ScreeningService(sqlite_session).screen(
        ScreenRequest(
            roe_min=Decimal("0.15"),
            pe_max=Decimal("30"),
            revenue_growth_min=Decimal("0.10"),
        )
    )
    assert [hit.ticker for hit in result.items] == ["GOOGL", "META"]
    assert result.total == 2
    assert result.applied.roe_min == Decimal("0.15")


def test_empty_screen_returns_all_with_fundamentals(
    sqlite_session: Session,
) -> None:
    _seed_seven(sqlite_session)
    orphan = _security(sqlite_session, "ORPH")
    assert orphan.fundamental is None
    result = ScreeningService(sqlite_session).screen(ScreenRequest())
    assert result.total == 7
    assert "ORPH" not in [hit.ticker for hit in result.items]


def test_pagination_is_stable_by_ticker(sqlite_session: Session) -> None:
    _seed_seven(sqlite_session)
    first = ScreeningService(sqlite_session).screen(
        ScreenRequest(
            roe_min=Decimal("0.15"),
            pe_max=Decimal("30"),
            revenue_growth_min=Decimal("0.10"),
            limit=1,
            offset=0,
        )
    )
    second = ScreeningService(sqlite_session).screen(
        ScreenRequest(
            roe_min=Decimal("0.15"),
            pe_max=Decimal("30"),
            revenue_growth_min=Decimal("0.10"),
            limit=1,
            offset=1,
        )
    )
    assert first.total == 2
    assert first.items[0].ticker == "GOOGL"
    assert second.items[0].ticker == "META"


def test_sector_filter_is_case_insensitive(sqlite_session: Session) -> None:
    _seed_seven(sqlite_session)
    result = ScreeningService(sqlite_session).screen(
        ScreenRequest(sector="technology")
    )
    assert {hit.ticker for hit in result.items} == {"AAPL", "MSFT", "NVDA"}


def test_industry_filter_uses_stored_security_value(
    sqlite_session: Session,
) -> None:
    chip = _security(sqlite_session, "NVDA", industry="Semiconductors")
    software = _security(sqlite_session, "MSFT", industry="Software")
    for security in (chip, software):
        _fundamentals(
            sqlite_session,
            security,
            roe="0.30",
            pe="25",
            growth="0.20",
            mcap="100",
        )
    result = ScreeningService(sqlite_session).screen(
        ScreenRequest(industry="semiconductors")
    )
    assert [hit.ticker for hit in result.items] == ["NVDA"]
    assert result.items[0].industry == "Semiconductors"


def test_controlled_sort_has_stable_ticker_tie_breaker(
    sqlite_session: Session,
) -> None:
    for ticker in ("MSFT", "AAPL", "NVDA"):
        security = _security(sqlite_session, ticker)
        _fundamentals(
            sqlite_session,
            security,
            roe="0.30",
            pe="25",
            growth="0.20",
            mcap="100",
        )
    result = ScreeningService(sqlite_session).screen(
        ScreenRequest(sort_by="market_cap", sort_direction="desc")
    )
    assert [hit.ticker for hit in result.items] == ["AAPL", "MSFT", "NVDA"]


def test_request_rejects_sql_shaped_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ScreenRequest.model_validate({"roe_min": "0.15", "query": "OR 1=1"})


def test_request_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError, match="roe_min"):
        ScreenRequest.model_validate({"roe_min": "0.40", "roe_max": "0.10"})


def test_screening_second_read_is_a_cache_hit(sqlite_session: Session) -> None:
    _seed_seven(sqlite_session)
    cache = FakeCache()
    service = ScreeningService(sqlite_session, cache)
    payload = ScreenRequest(roe_min=Decimal("0.15"), pe_max=Decimal("30"))

    first = service.screen(payload)

    def fail_if_database_is_called(*_args, **_kwargs):
        raise AssertionError("screening repository should not run on cache hit")

    service.fundamentals.screen = fail_if_database_is_called
    second = service.screen(payload)

    assert second == first
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 1
    assert cache.stats()["sets"] == 1


def test_fundamentals_version_changes_screen_cache_key(
    sqlite_session: Session,
) -> None:
    _seed_seven(sqlite_session)
    cache = FakeCache()
    service = ScreeningService(sqlite_session, cache)
    payload = ScreenRequest(sector="Technology")

    before = service._cache_key(payload)
    cache.bump_version("fundamentals")
    after = service._cache_key(payload)

    assert before != after
