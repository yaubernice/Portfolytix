from decimal import Decimal
from uuid import uuid4

from app.services.holdings import PositionLeg, aggregate_positions, quantity_held


def test_buy_buy_sell_matches_spec_example() -> None:
    apple = uuid4()
    legs = [
        PositionLeg(apple, "AAPL", "BUY", Decimal("10")),
        PositionLeg(apple, "AAPL", "BUY", Decimal("5")),
        PositionLeg(apple, "AAPL", "SELL", Decimal("3")),
    ]
    holdings = aggregate_positions(legs)
    assert len(holdings) == 1
    assert holdings[0].ticker == "AAPL"
    assert holdings[0].quantity == Decimal("12")
    assert quantity_held(holdings, apple) == Decimal("12")


def test_zero_position_is_omitted() -> None:
    apple = uuid4()
    legs = [
        PositionLeg(apple, "AAPL", "BUY", Decimal("2")),
        PositionLeg(apple, "AAPL", "SELL", Decimal("2")),
    ]
    assert aggregate_positions(legs) == []


def test_multiple_tickers_sorted_by_symbol() -> None:
    apple = uuid4()
    nvidia = uuid4()
    legs = [
        PositionLeg(nvidia, "NVDA", "BUY", Decimal("1")),
        PositionLeg(apple, "AAPL", "BUY", Decimal("2")),
    ]
    tickers = [row.ticker for row in aggregate_positions(legs)]
    assert tickers == ["AAPL", "NVDA"]
