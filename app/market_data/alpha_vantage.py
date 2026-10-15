"""Alpha Vantage TIME_SERIES_DAILY adapter.

Free daily bars do not include split-adjusted close; we store
``adjusted_close = close`` unless the payload has ``5. adjusted close``.
The API key is never logged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from app.core.config import settings
from app.market_data.capabilities import ALPHA_VANTAGE
from app.market_data.errors import ProviderError
from app.market_data.news import news_record
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar
from app.quotes.models import LiveQuote, quote_from_parts

BASE_URL = "https://www.alphavantage.co/query"
SERIES_KEY = "Time Series (Daily)"


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    capabilities = ALPHA_VANTAGE

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "MARKET_DATA_API_KEY is empty; set it, or use stooq for "
                "daily bars and QUOTE_PROVIDER=simulator for live quotes",
                retryable=False,
            )
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=30.0)

    def fetch_daily_bars(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> list[RawBar]:
        symbol = ticker.upper()
        span = (end - start).days
        # `full` downloads the vendor's entire daily history. Use it only
        # when that older window was explicitly allowed.
        outputsize = "compact"
        if span > 100 and settings.market_data_allow_full_history:
            outputsize = "full"
        payload = self._get_json(symbol, outputsize=outputsize)
        return parse_alpha_vantage_daily(payload, symbol, start, end)

    def fetch_quotes(self, tickers: list[str]) -> list[LiveQuote]:
        quotes: list[LiveQuote] = []
        for ticker in tickers:
            symbol = ticker.upper()
            payload = self._get(
                {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self._api_key},
                symbol,
            )
            quotes.append(parse_alpha_vantage_quote(payload, symbol))
        return quotes

    def fetch_overview(self, ticker: str) -> dict[str, Decimal | None]:
        symbol = ticker.upper()
        payload = self._get(
            {"function": "OVERVIEW", "symbol": symbol, "apikey": self._api_key},
            symbol,
        )
        return parse_alpha_vantage_overview(payload, symbol)

    def fetch_news(self, ticker: str) -> list[dict]:
        symbol = ticker.upper()
        payload = self._get(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": "8",
                "apikey": self._api_key,
            },
            symbol,
        )
        return parse_alpha_vantage_news(payload, symbol)

    def _get(self, params: dict[str, str], symbol: str) -> dict:
        response = self._client.get(BASE_URL, params=params)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Alpha Vantage HTTP error for {symbol}") from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"Alpha Vantage payload is not an object for {symbol}",
                retryable=False,
            )
        _raise_for_vendor_note(payload, symbol)
        return payload

    def _get_json(self, symbol: str, outputsize: str) -> dict:
        response = self._client.get(
            BASE_URL,
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": outputsize,
                "apikey": self._api_key,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Alpha Vantage HTTP error for {symbol}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                f"Alpha Vantage returned non-JSON for {symbol}",
                retryable=False,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"Alpha Vantage payload is not an object for {symbol}",
                retryable=False,
            )
        return payload


def parse_alpha_vantage_daily(
    payload: dict,
    ticker: str,
    start: date,
    end: date,
) -> list[RawBar]:
    """Turn a TIME_SERIES_DAILY JSON body into RawBar rows. No HTTP here."""
    if payload.get("Note") or payload.get("Information"):
        raise ProviderError(
            f"Alpha Vantage rate-limited or blocked for {ticker}"
        )
    error = payload.get("Error Message")
    if error:
        raise ProviderError(
            f"Alpha Vantage rejected {ticker}: {error}",
            retryable=False,
        )
    series = payload.get(SERIES_KEY)
    if not isinstance(series, dict):
        raise ProviderError(
            f"Alpha Vantage missing time series for {ticker}",
            retryable=False,
        )

    bars: list[RawBar] = []
    for day_text, fields in series.items():
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day < start or day > end:
            continue
        if not isinstance(fields, dict):
            continue
        try:
            close = Decimal(str(fields["4. close"]))
            adjusted_text = fields.get("5. adjusted close")
            if adjusted_text not in (None, ""):
                adjusted = Decimal(str(adjusted_text))
                volume_text = fields["6. volume"]
            else:
                # TIME_SERIES_DAILY has no adjusted close. Do not invent one.
                adjusted = close
                volume_text = fields["5. volume"]
            bars.append(
                RawBar(
                    ticker=ticker,
                    day=day,
                    open=Decimal(str(fields["1. open"])),
                    high=Decimal(str(fields["2. high"])),
                    low=Decimal(str(fields["3. low"])),
                    close=close,
                    adjusted_close=adjusted,
                    volume=int(Decimal(str(volume_text))),
                )
            )
        except (KeyError, ArithmeticError, ValueError):
            continue
    bars.sort(key=lambda bar: bar.day)
    return bars


def parse_alpha_vantage_quote(payload: dict, ticker: str) -> LiveQuote:
    """GLOBAL_QUOTE is the latest daily/delayed price unless the key is entitled."""
    _raise_for_vendor_note(payload, ticker)
    raw = payload.get("Global Quote")
    if not isinstance(raw, dict):
        raise ProviderError(
            f"Alpha Vantage missing Global Quote for {ticker}",
            retryable=False,
        )
    try:
        price = Decimal(str(raw["05. price"]))
        previous_text = raw.get("08. previous close")
        previous = None
        if previous_text not in (None, ""):
            previous = Decimal(str(previous_text))
        volume = int(Decimal(str(raw["06. volume"])))
        day = date.fromisoformat(str(raw["07. latest trading day"]))
    except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
        raise ProviderError(
            f"Alpha Vantage quote for {ticker} is incomplete",
            retryable=False,
        ) from exc
    if price <= 0 or not price.is_finite():
        raise ProviderError(
            f"Alpha Vantage quote for {ticker} has no last price",
            retryable=False,
        )
    return quote_from_parts(
        ticker=ticker,
        price=price,
        previous_close=previous,
        volume=volume,
        timestamp=datetime(day.year, day.month, day.day, tzinfo=UTC),
        source="alpha_vantage",
        timeliness="realtime" if settings.alpha_vantage_realtime else "delayed",
    )


def parse_alpha_vantage_overview(
    payload: dict,
    ticker: str,
) -> dict[str, Decimal | None]:
    """Map OVERVIEW onto the fundamental columns. Missing fields stay null."""
    _raise_for_vendor_note(payload, ticker)
    if not payload.get("Symbol"):
        raise ProviderError(
            f"Alpha Vantage overview for {ticker} is empty",
            retryable=False,
        )

    def _decimal(key: str) -> Decimal | None:
        text = payload.get(key)
        if text in (None, "", "None", "-"):
            return None
        try:
            return Decimal(str(text))
        except ArithmeticError:
            return None

    # OVERVIEW ratios are already decimals (0.15) except MarketCapitalization.
    return {
        "roe": _decimal("ReturnOnEquityTTM"),
        "pe_ratio": _decimal("PERatio"),
        "revenue_growth": _decimal("QuarterlyRevenueGrowthYOY"),
        "market_cap": _decimal("MarketCapitalization"),
        "eps": _decimal("EPS"),
        "revenue": _decimal("RevenueTTM"),
        "profit_margin": _decimal("ProfitMargin"),
        "dividend_yield": _decimal("DividendYield"),
        "beta": _decimal("Beta"),
        "ebitda": _decimal("EBITDA"),
        "shares_outstanding": _decimal("SharesOutstanding"),
        "price_to_book": _decimal("PriceToBookRatio"),
        "price_to_sales": _decimal("PriceToSalesRatioTTM"),
        "roa": _decimal("ReturnOnAssetsTTM"),
        "earnings_growth": _decimal("QuarterlyEarningsGrowthYOY"),
    }


def parse_alpha_vantage_news(payload: dict, ticker: str) -> list[dict]:
    _raise_for_vendor_note(payload, ticker)
    feed = payload.get("feed")
    if not isinstance(feed, list):
        raise ProviderError(
            f"Alpha Vantage news for {ticker} has no feed",
            retryable=False,
        )
    items: list[dict] = []
    for row in feed:
        if not isinstance(row, dict):
            continue
        headline = row.get("title")
        if not isinstance(headline, str) or not headline.strip():
            continue
        related = [ticker]
        sentiment = row.get("overall_sentiment_label")
        entries = row.get("ticker_sentiment")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("ticker"), str):
                    related.append(entry["ticker"])
        image = row.get("banner_image")
        items.append(
            news_record(
                headline=headline,
                summary=str(row.get("summary") or ""),
                source=str(row.get("source") or "alpha_vantage"),
                url=str(row.get("url") or ""),
                published_at=str(row.get("time_published") or ""),
                tickers=related,
                sentiment=sentiment if isinstance(sentiment, str) else None,
                provider="alpha_vantage",
                image_url=image if isinstance(image, str) else "",
            )
        )
    return items


def _raise_for_vendor_note(payload: dict, ticker: str) -> None:
    if payload.get("Note") or payload.get("Information"):
        raise ProviderError(f"Alpha Vantage rate-limited or blocked for {ticker}")
    error = payload.get("Error Message")
    if error:
        raise ProviderError(
            f"Alpha Vantage rejected {ticker}: {error}",
            retryable=False,
        )
