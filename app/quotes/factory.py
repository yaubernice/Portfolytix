from __future__ import annotations

from app.core.config import settings
from app.market_data.alpha_vantage import AlphaVantageProvider
from app.market_data.errors import ProviderError
from app.market_data.finnhub import FinnhubQuoteSource
from app.market_data.yahoo_news import YahooNewsSource
from app.quotes.simulator import SimulatorQuoteSource


def quote_symbols() -> list[str]:
    return [
        part.strip().upper()
        for part in settings.quote_symbols.split(",")
        if part.strip()
    ]


def build_news_source():
    """Headline adapter. The simulator has no news source and invents nothing."""
    chosen = settings.news_provider.strip().lower()
    if chosen == "none":
        return None
    if chosen == "finnhub":
        key = settings.finnhub_api_key or settings.market_data_api_key
        return FinnhubQuoteSource(key)
    if chosen == "alpha_vantage":
        return AlphaVantageProvider(settings.market_data_api_key)
    if chosen == "yahoo":
        return YahooNewsSource()
    if chosen != "":
        raise ProviderError(
            "Unknown NEWS_PROVIDER="
            f"{chosen!r}; use an empty value, none, yahoo, finnhub, "
            "or alpha_vantage",
            retryable=False,
        )
    source = build_quote_source()
    capabilities = getattr(source, "capabilities", None)
    if capabilities is not None and capabilities.supports_news:
        return source
    return None


def build_quote_source(
    name: str | None = None,
):
    """Pick the live-quote adapter. Daily-bar ingest keeps its own provider."""
    chosen = (name or settings.quote_provider).strip().lower()
    if chosen == "simulator":
        return SimulatorQuoteSource()
    if chosen == "alpha_vantage":
        return AlphaVantageProvider(settings.market_data_api_key)
    if chosen == "finnhub":
        key = settings.finnhub_api_key or settings.market_data_api_key
        return FinnhubQuoteSource(key)
    raise ProviderError(
        "Unknown QUOTE_PROVIDER="
        f"{chosen!r}; use simulator, finnhub, or alpha_vantage",
        retryable=False,
    )
