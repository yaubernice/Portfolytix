from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.analytics import (
    CloseBar,
    Fill,
    allocation,
    annualized_volatility,
    build_value_series,
    daily_profit_loss,
    daily_returns_of,
    max_drawdown,
    point_in_time_drawdowns,
    sample_stdev,
    sharpe_ratio,
    total_return,
)

APPLE = uuid4()
MSFT = uuid4()


def test_twr_ignores_the_buy_cash_flow() -> None:
    """Buy 1 share at 100; next close 110 → 10% TWR, not a 10% 'deposit gain'."""
    fills = [
        Fill(
            on=date(2024, 1, 2),
            security_id=APPLE,
            ticker="AAPL",
            is_buy=True,
            quantity=Decimal("1"),
            price=Decimal("100"),
        )
    ]
    bars = [
        CloseBar(APPLE, date(2024, 1, 2), Decimal("100")),
        CloseBar(APPLE, date(2024, 1, 3), Decimal("110")),
    ]
    points = build_value_series(fills, bars)
    returns = daily_returns_of(points)
    assert returns == [Decimal("0.1")]
    assert total_return(returns) == Decimal("0.1")
    assert points[0].daily_return is None
    assert points[0].value == Decimal("100")
    assert points[1].value == Decimal("110")


def test_second_buy_does_not_inflate_twr() -> None:
    """Day2 buy at the close should not create a spurious return."""
    fills = [
        Fill(
            on=date(2024, 1, 2),
            security_id=APPLE,
            ticker="AAPL",
            is_buy=True,
            quantity=Decimal("1"),
            price=Decimal("100"),
        ),
        Fill(
            on=date(2024, 1, 3),
            security_id=APPLE,
            ticker="AAPL",
            is_buy=True,
            quantity=Decimal("1"),
            price=Decimal("110"),
        ),
    ]
    bars = [
        CloseBar(APPLE, date(2024, 1, 2), Decimal("100")),
        CloseBar(APPLE, date(2024, 1, 3), Decimal("110")),
        CloseBar(APPLE, date(2024, 1, 4), Decimal("121")),
    ]
    returns = daily_returns_of(build_value_series(fills, bars))
    assert returns == [Decimal("0.1"), Decimal("0.1")]
    assert total_return(returns) == Decimal("0.21")


def test_max_drawdown_from_peak() -> None:
    # wealth 1 → 1.2 → 0.9  ⇒  0.9/1.2 − 1 = −25%
    result = max_drawdown([Decimal("0.2"), Decimal("-0.25")])
    assert result == Decimal("-0.25")


def test_max_drawdown_never_positive() -> None:
    assert max_drawdown([Decimal("0.05"), Decimal("0.01")]) == Decimal("0")


def test_daily_profit_loss_removes_external_cash_flow() -> None:
    assert daily_profit_loss(
        Decimal("100"),
        Decimal("165"),
        Decimal("50"),
    ) == Decimal("15")
    assert daily_profit_loss(None, Decimal("100"), Decimal("100")) is None


def test_point_in_time_drawdown_path_uses_twr_wealth() -> None:
    path = point_in_time_drawdowns(
        [None, Decimal("0.2"), Decimal("-0.25"), Decimal("0.1")]
    )
    assert path == [
        Decimal("0"),
        Decimal("0"),
        Decimal("-0.25"),
        Decimal("-0.175"),
    ]


def test_sample_stdev_needs_two_points() -> None:
    assert sample_stdev([Decimal("0.01")]) is None
    assert sample_stdev([Decimal("0.01"), Decimal("0.01")]) == Decimal("0")


def test_volatility_and_sharpe_undefined_when_flat() -> None:
    daily = [Decimal("0.01"), Decimal("0.01")]
    assert annualized_volatility(daily) is None or annualized_volatility(daily) == 0
    # zero sample stdev → Sharpe is undefined, not infinity
    assert sharpe_ratio(daily) is None


def test_sharpe_positive_when_mean_beats_rf() -> None:
    daily = [Decimal("0.02"), Decimal("0.00")]
    ratio = sharpe_ratio(daily, risk_free_rate_annual=Decimal("0.05"))
    assert ratio is not None
    assert ratio > 0


def test_allocation_is_market_value_weights() -> None:
    lines = allocation(
        quantities={APPLE: Decimal("10"), MSFT: Decimal("5")},
        tickers={APPLE: "AAPL", MSFT: "MSFT"},
        prices={APPLE: Decimal("2"), MSFT: Decimal("4")},
    )
    by_ticker = {line.ticker: line for line in lines}
    assert by_ticker["AAPL"].weight == Decimal("0.5")
    assert by_ticker["MSFT"].weight == Decimal("0.5")
    assert [line.ticker for line in lines] == ["AAPL", "MSFT"]
