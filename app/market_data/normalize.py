from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from app.market_data.types import NormalizedBar, RawBar

PRICE_SCALE = Decimal("0.000001")


def normalize_bar(raw: RawBar) -> tuple[NormalizedBar | None, str | None]:
    """Validate and quantize one bar. Returns ``(None, reason)`` if dropped."""
    if raw.high < raw.low:
        return None, "high_below_low"
    prices = (raw.open, raw.high, raw.low, raw.close, raw.adjusted_close)
    if any(price <= 0 for price in prices):
        return None, "non_positive_price"
    if raw.volume < 0:
        return None, "negative_volume"

    timestamp = datetime(raw.day.year, raw.day.month, raw.day.day, tzinfo=UTC)
    return (
        NormalizedBar(
            day=raw.day,
            timestamp=timestamp,
            open=_money(raw.open),
            high=_money(raw.high),
            low=_money(raw.low),
            close=_money(raw.close),
            adjusted_close=_money(raw.adjusted_close),
            volume=raw.volume,
        ),
        None,
    )


def _money(value: Decimal) -> Decimal:
    quantized = value.quantize(PRICE_SCALE, rounding=ROUND_HALF_EVEN)
    if quantized <= 0:
        return PRICE_SCALE
    return quantized
