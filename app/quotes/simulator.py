from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.seed import SECURITIES
from app.market_data.capabilities import SIMULATOR
from app.quotes.models import LiveQuote, quote_from_parts

# Seed start prices are the previous close. The price oscillates around
# that close so a long-running demo does not walk the symbol to zero.


class SimulatorQuoteSource:
    name = "simulator"
    capabilities = SIMULATOR

    def __init__(self) -> None:
        self._previous = {
            spec.ticker: spec.start_price for spec in SECURITIES
        }
        self._step = 0

    def fetch_quotes(self, tickers: list[str]) -> list[LiveQuote]:
        self._step += 1
        # -5..4, so the sign flips as the worker keeps polling.
        cycle = Decimal((self._step % 10) - 5)
        now = datetime.now(UTC)
        quotes: list[LiveQuote] = []
        for ticker in tickers:
            symbol = ticker.upper()
            previous = self._previous.get(symbol, Decimal("100"))
            price = (previous + previous * Decimal("0.002") * cycle).quantize(
                Decimal("0.01")
            )
            if price <= 0:
                price = Decimal("0.01")
            quotes.append(
                quote_from_parts(
                    ticker=symbol,
                    price=price,
                    previous_close=previous,
                    volume=1_000 * self._step,
                    timestamp=now,
                    source=self.name,
                    timeliness="simulated",
                )
            )
        return quotes
