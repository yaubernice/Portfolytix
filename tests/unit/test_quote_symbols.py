from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Security, User, Watchlist, WatchlistItem
from app.quotes.factory import build_news_source
from app.quotes.simulator import SimulatorQuoteSource
from app.quotes.symbols import (
    load_quote_symbols,
    normalize_quote_symbols,
    subscription_delta,
)


def test_simulator_quotes_are_not_called_realtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "news_provider", "")
    monkeypatch.setattr(settings, "quote_provider", "simulator")
    assert build_news_source() is None
    quote = SimulatorQuoteSource().fetch_quotes(["AAPL"])[0]
    assert quote.timeliness == "simulated"
    assert quote.source == "simulator"


def test_watchlist_membership_replaces_the_demo_list(
    sqlite_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "quote_max_symbols", 1)
    user = User(email="quotes@example.com", password_hash="x")
    apple = Security(
        ticker="AAPL",
        name="Apple",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    nvidia = Security(
        ticker="NVDA",
        name="NVIDIA",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    msft = Security(
        ticker="MSFT",
        name="Microsoft",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
        is_active=False,
    )
    sqlite_session.add_all([user, apple, nvidia, msft])
    sqlite_session.flush()
    watchlist = Watchlist(user_id=user.id, name="Ideas")
    sqlite_session.add(watchlist)
    sqlite_session.flush()
    for security in (apple, nvidia, msft):
        sqlite_session.add(
            WatchlistItem(watchlist_id=watchlist.id, security_id=security.id)
        )
    sqlite_session.flush()
    assert load_quote_symbols(sqlite_session) == ["AAPL"]


def test_empty_watchlists_use_the_configured_demo_list(
    sqlite_session: Session,
) -> None:
    assert load_quote_symbols(sqlite_session) == [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
    ]


def test_subscription_delta_adds_and_drops() -> None:
    added, removed = subscription_delta(
        {"AAPL", "MSFT"},
        ["AAPL", "NVDA", "nvda"],
    )
    assert added == ["NVDA"]
    assert removed == ["MSFT"]


def test_quote_symbol_filter_normalizes_deduplicates_and_limits() -> None:
    assert normalize_quote_symbols(" msft,AAPL,msft ", limit=3) == [
        "MSFT",
        "AAPL",
    ]
    try:
        normalize_quote_symbols("AAPL;DROP", limit=3)
    except ValueError as exc:
        assert "Invalid quote ticker" in str(exc)
    else:
        raise AssertionError("invalid ticker was accepted")
    try:
        normalize_quote_symbols("AAPL,MSFT", limit=1)
    except ValueError as exc:
        assert "At most 1" in str(exc)
    else:
        raise AssertionError("symbol limit was not enforced")
