from datetime import date
from decimal import Decimal

from app.db.seed import SECURITIES, generate_daily_bars, iter_weekdays


def test_reference_universe_matches_phase_two_spec() -> None:
    tickers = [spec.ticker for spec in SECURITIES]
    assert tickers == ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def test_weekdays_skip_weekends() -> None:
    days = list(iter_weekdays(date(2024, 1, 5), date(2024, 1, 8)))
    assert days == [date(2024, 1, 5), date(2024, 1, 8)]


def test_generated_bars_are_deterministic_and_valid() -> None:
    first = generate_daily_bars(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        start_price=Decimal("185"),
        rng_seed=11,
    )
    second = generate_daily_bars(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        start_price=Decimal("185"),
        rng_seed=11,
    )
    assert first == second
    assert len(first) >= 60
    for bar in first:
        assert isinstance(bar["close"], Decimal)
        assert bar["high"] >= bar["low"]
        assert bar["open"] > 0
        assert bar["close"] > 0
        assert bar["volume"] >= 0
        assert bar["timestamp"].weekday() < 5


def test_two_year_seed_window_has_hundreds_of_bars() -> None:
    bars = generate_daily_bars(
        start=date(2024, 1, 2),
        end=date(2025, 12, 31),
        start_price=Decimal("100"),
        rng_seed=1,
    )
    assert 500 <= len(bars) <= 530
