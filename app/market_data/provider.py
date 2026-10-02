from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.market_data.types import RawBar


class MarketDataProvider(ABC): #abstract base class for all market data providers
    """Vendor adapter. Ingest and Postgres do not import a specific API."""

    name: str

    @abstractmethod
    # every provider returns daily bars for the ticker in [start, end]
    def fetch_daily_bars(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> list[RawBar]:
        # list of raw bars for the ticker between the start and end dates
        """Return raw daily bars in ``[start, end]`` inclusive.

        Implementations may over-fetch and filter. They must not write
        to the database. Raise ``ProviderError`` on vendor failure.
        """
