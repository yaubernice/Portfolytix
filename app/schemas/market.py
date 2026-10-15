from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.quotes.models import LiveQuote
from app.schemas.common import DecimalStr, OptionalDecimalStr


class QuotesResponse(BaseModel):
    quotes: list[LiveQuote]


class NewsItem(BaseModel):
    headline: str
    summary: str = ""
    source: str
    url: str = ""
    published_at: str = ""
    tickers: list[str] = []
    sentiment: str | None = None
    provider: str = ""
    image_url: str = ""


class NewsResponse(BaseModel):
    ticker: str
    security_id: UUID | None = None
    source: str
    provider: str = "none"
    items: list[NewsItem]


class PortfolioNewsResponse(BaseModel):
    portfolio_id: UUID
    provider: str = "none"
    note: str
    items: list[NewsItem]
    unavailable: list[str] = []


class PriceBarOut(BaseModel):
    date: date
    close: DecimalStr
    volume: int


class HistoricalFreshness(BaseModel):
    """Stored daily bars. This is never a live quote."""

    security_id: UUID
    ticker: str
    latest_bar: date | None
    source: str | None
    last_successful_update: datetime | None
    timeliness: str
    is_stale: bool = False


class SecurityProfile(BaseModel):
    security_id: UUID
    ticker: str
    name: str
    exchange: str
    mic: str | None = None
    sector: str
    industry: str | None = None
    country: str | None = None
    currency: str
    asset_type: str = "equity"
    provider: str = "manual"
    provider_symbol: str = ""
    is_active: bool = True
    as_of: date | None = None
    roe: OptionalDecimalStr = None
    pe_ratio: OptionalDecimalStr = None
    revenue_growth: OptionalDecimalStr = None
    market_cap: OptionalDecimalStr = None
    eps: OptionalDecimalStr = None
    revenue: OptionalDecimalStr = None
    profit_margin: OptionalDecimalStr = None
    dividend_yield: OptionalDecimalStr = None
    beta: OptionalDecimalStr = None
    ebitda: OptionalDecimalStr = None
    shares_outstanding: OptionalDecimalStr = None
    price_to_book: OptionalDecimalStr = None
    price_to_sales: OptionalDecimalStr = None
    roa: OptionalDecimalStr = None
    earnings_growth: OptionalDecimalStr = None
    fundamentals_provider: str | None = None
    fundamentals_updated_at: datetime | None = None
    latest_close: OptionalDecimalStr = None
    latest_close_at: datetime | None = None
    history_source: str | None = None
    history_updated_at: datetime | None = None
    history_timeliness: str = "unavailable"
    history_is_stale: bool = False
    live_quote: LiveQuote | None = None
    live_timeliness: str = "unavailable"
    prices: list[PriceBarOut]
