from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """What a vendor adapter can actually do. Unset means unsupported."""

    supports_realtime_stream: bool = False
    supports_delayed_quote: bool = False
    supports_historical: bool = False
    supports_fundamentals: bool = False
    supports_news: bool = False


SIMULATOR = ProviderCapabilities()

FINNHUB = ProviderCapabilities(
    supports_realtime_stream=True,
    supports_delayed_quote=True,
    supports_news=True,
)

ALPHA_VANTAGE = ProviderCapabilities(
    supports_delayed_quote=True,
    supports_historical=True,
    supports_fundamentals=True,
    supports_news=True,
)

STOOQ = ProviderCapabilities(supports_historical=True)

YAHOO_NEWS = ProviderCapabilities(supports_news=True)

YAHOO_HISTORY = ProviderCapabilities(supports_historical=True)
