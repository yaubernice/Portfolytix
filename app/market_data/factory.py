from __future__ import annotations

import httpx

from app.core.config import settings
from app.market_data.alpha_vantage import AlphaVantageProvider
from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.stooq import StooqProvider
from app.market_data.yahoo_history import YahooHistoryProvider


def build_provider(
    name: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> MarketDataProvider:
    """Construct the configured vendor adapter. Default is settings."""
    chosen = (name or settings.market_data_provider).strip().lower()
    if chosen == "alpha_vantage":
        return AlphaVantageProvider(settings.market_data_api_key, client=client)
    if chosen == "stooq":
        return StooqProvider(client=client)
    if chosen == "yahoo":
        return YahooHistoryProvider(client=client)
    raise ProviderError(
        f"Unknown MARKET_DATA_PROVIDER={chosen!r}; use yahoo, stooq, or alpha_vantage",
        retryable=False,
    )
