from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.db.models import ASSET_TYPES, Fundamental, Price, Security
from app.market_data.calendar import bar_is_stale
from app.market_data.errors import ProviderError
from app.market_data.yahoo_history import YahooHistoryProvider
from app.quotes.factory import build_news_source
from app.quotes.store import QuoteStore, QuoteStoreError
from app.repositories.price_repository import PriceRepository
from app.repositories.security_repository import SecurityQuery, SecurityRepository
from app.schemas.market import (
    HistoricalFreshness,
    NewsItem,
    NewsResponse,
    PortfolioNewsResponse,
    PriceBarOut,
    SecurityProfile,
)
from app.schemas.security import SecurityOut, SecurityPage
from app.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class ReferenceService:
    """Read durable security history and the Redis news cache."""

    def __init__(self, session: Session, quotes: QuoteStore) -> None:
        self.session = session
        self.securities = SecurityRepository(session)
        self.prices = PriceRepository(session)
        self.quotes = quotes

    def get(self, security_id: UUID) -> SecurityOut:
        security = self.securities.get_by_id(security_id)
        if security is None:
            raise NotFoundError(f"Security {security_id} not found")
        return SecurityOut.model_validate(security)

    def search(
        self,
        *,
        q: str | None,
        exchange: str | None,
        country: str | None,
        sector: str | None,
        asset_type: str | None,
        limit: int,
        offset: int,
    ) -> SecurityPage:
        chosen = None
        if asset_type and asset_type.strip():
            chosen = asset_type.strip().lower()
        if chosen is not None and chosen not in ASSET_TYPES:
            raise AppError(
                f"asset_type must be one of: {', '.join(ASSET_TYPES)}",
                status_code=422,
            )
        rows, total = self.securities.search(
            SecurityQuery(
                q=q,
                exchange=exchange,
                country=country,
                sector=sector,
                asset_type=chosen,
                limit=limit,
                offset=offset,
            )
        )
        return SecurityPage(
            items=[SecurityOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def profile(
        self,
        ticker: str,
        *,
        history_period: Literal["1D", "1W", "1M", "3M", "1Y", "MAX"] | None = None,
        price_limit: int = 90,
        ensure_history: bool = False,
    ) -> SecurityProfile:
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker.upper()} not found")
        if ensure_history and self.prices.latest(security.id) is None:
            self._fill_missing_history(security.ticker)
        fundamental = self.session.scalar(
            select(Fundamental).where(Fundamental.security_id == security.id)
        )
        history_query = (
            select(Price)
            .where(Price.security_id == security.id)
            .order_by(Price.timestamp.desc())
        )
        latest_price = self.prices.latest(security.id)
        if history_period and history_period != "MAX" and latest_price is not None:
            period_days = {
                "1D": 0,
                "1W": 7,
                "1M": 31,
                "3M": 92,
                "1Y": 366,
            }
            history_query = history_query.where(
                Price.timestamp
                >= latest_price.timestamp - timedelta(days=period_days[history_period])
            )
        bars = list(
            self.session.scalars(
                history_query.limit(price_limit)
            )
        )
        bars.reverse()
        latest = bars[-1] if bars else None
        live_quotes = self.quotes.snapshot([security.ticker])
        live_quote = live_quotes[0] if live_quotes else None
        history_updated = self.prices.last_ingested_at(security.id)
        timeliness, history_stale = _bar_freshness(latest.timestamp if latest else None)
        return SecurityProfile(
            security_id=security.id,
            ticker=security.ticker,
            name=security.name,
            exchange=security.exchange,
            mic=security.mic,
            sector=security.sector,
            industry=security.industry,
            country=security.country,
            currency=security.currency,
            asset_type=security.asset_type,
            provider=security.provider,
            provider_symbol=security.provider_symbol,
            is_active=security.is_active,
            as_of=fundamental.as_of if fundamental is not None else None,
            roe=fundamental.roe if fundamental is not None else None,
            pe_ratio=fundamental.pe_ratio if fundamental is not None else None,
            revenue_growth=(
                fundamental.revenue_growth if fundamental is not None else None
            ),
            market_cap=fundamental.market_cap if fundamental is not None else None,
            eps=fundamental.eps if fundamental is not None else None,
            revenue=fundamental.revenue if fundamental is not None else None,
            profit_margin=(
                fundamental.profit_margin if fundamental is not None else None
            ),
            dividend_yield=(
                fundamental.dividend_yield if fundamental is not None else None
            ),
            beta=fundamental.beta if fundamental is not None else None,
            ebitda=fundamental.ebitda if fundamental is not None else None,
            shares_outstanding=(
                fundamental.shares_outstanding if fundamental is not None else None
            ),
            price_to_book=(
                fundamental.price_to_book if fundamental is not None else None
            ),
            price_to_sales=(
                fundamental.price_to_sales if fundamental is not None else None
            ),
            roa=fundamental.roa if fundamental is not None else None,
            earnings_growth=(
                fundamental.earnings_growth if fundamental is not None else None
            ),
            fundamentals_provider=(
                fundamental.provider if fundamental is not None else None
            ),
            fundamentals_updated_at=(
                fundamental.updated_at if fundamental is not None else None
            ),
            latest_close=latest.adjusted_close if latest is not None else None,
            latest_close_at=latest.timestamp if latest is not None else None,
            history_source=latest.source if latest is not None else None,
            history_updated_at=history_updated,
            history_timeliness=timeliness,
            history_is_stale=history_stale,
            live_quote=live_quote,
            live_timeliness=(
                live_quote.timeliness if live_quote is not None else "unavailable"
            ),
            prices=[
                PriceBarOut(
                    date=bar.timestamp.date(),
                    close=bar.adjusted_close,
                    volume=bar.volume,
                )
                for bar in bars
            ],
        )

    def historical_freshness(self, ticker: str) -> HistoricalFreshness:
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker.upper()} not found")
        latest = self.prices.latest(security.id)
        updated = self.prices.last_ingested_at(security.id)
        if latest is None:
            return HistoricalFreshness(
                security_id=security.id,
                ticker=security.ticker,
                latest_bar=None,
                source=None,
                last_successful_update=None,
                timeliness="unavailable",
                is_stale=False,
            )
        timeliness, stale = _bar_freshness(latest.timestamp)
        return HistoricalFreshness(
            security_id=security.id,
            ticker=security.ticker,
            latest_bar=latest.timestamp.date(),
            source=latest.source,
            last_successful_update=updated,
            timeliness=timeliness,
            is_stale=stale,
        )

    def news_for(self, security_id: UUID) -> NewsResponse:
        security = self.securities.get_by_id(security_id)
        if security is None:
            raise NotFoundError(f"Security {security_id} not found")
        return self._news(security)

    def news(self, ticker: str) -> NewsResponse:
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker.upper()} not found")
        return self._news(security)

    def news_for_holdings(
        self,
        portfolio_id: UUID,
        tickers: list[str],
    ) -> PortfolioNewsResponse:
        """Headlines for open positions. One symbol failing leaves the others."""
        symbols: list[str] = []
        for ticker in tickers:
            symbol = ticker.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        symbols = symbols[:8]
        if not symbols:
            return PortfolioNewsResponse(
                portfolio_id=portfolio_id,
                provider="none",
                note="This portfolio has no open positions.",
                items=[],
            )
        loaded = self._load_many(symbols)
        items: list[NewsItem] = []
        unavailable: list[str] = []
        provider = "none"
        for symbol in symbols:
            parsed = _parse_items(loaded.get(symbol, []))
            if not parsed:
                unavailable.append(symbol)
                continue
            if provider == "none" and parsed[0].provider:
                provider = parsed[0].provider
            items.extend(parsed)
        items.sort(key=lambda item: item.published_at or "", reverse=True)
        return PortfolioNewsResponse(
            portfolio_id=portfolio_id,
            provider=provider,
            note=_NEWS_NOTE,
            items=items,
            unavailable=unavailable,
        )

    def _news(self, security: Security) -> NewsResponse:
        symbol = security.ticker
        items = _parse_items(self._load_news(symbol))
        if not items:
            return NewsResponse(
                ticker=symbol,
                security_id=security.id,
                source="none",
                provider="none",
                items=[],
            )
        return NewsResponse(
            ticker=symbol,
            security_id=security.id,
            source=items[0].source,
            provider=items[0].provider or "none",
            items=items,
        )

    def _load_many(self, symbols: list[str]) -> dict[str, list[dict]]:
        if len(symbols) == 1:
            return {symbols[0]: self._load_news(symbols[0])}
        with ThreadPoolExecutor(max_workers=4) as pool:
            pairs = pool.map(
                lambda symbol: (symbol, self._load_news(symbol)),
                symbols,
            )
        return dict(pairs)

    def _load_news(self, symbol: str) -> list[dict]:
        cached = self.quotes.get_news(symbol)
        if cached:
            return [item for item in cached if isinstance(item, dict)]
        source = build_news_source()
        if source is None or not hasattr(source, "fetch_news"):
            return []
        try:
            if getattr(source, "name", "") == "finnhub":
                today = datetime.now(UTC).date()
                start = (today - timedelta(days=7)).isoformat()
                fetched = source.fetch_news(symbol, start, today.isoformat())
            else:
                fetched = source.fetch_news(symbol)
        except ProviderError:
            return []
        if not isinstance(fetched, list):
            return []
        stored = [item for item in fetched if isinstance(item, dict)][:8]
        if stored:
            try:
                self.quotes.put_news(symbol, stored)
            except QuoteStoreError:
                pass
        return stored

    def _fill_missing_history(self, ticker: str) -> None:
        """One symbol, daily bars only. A miss leaves the profile without a price.

        Stooq's file download currently returns a browser check, so this
        fill uses Yahoo's daily chart. It is a stored close, not a live quote.
        """
        end = datetime.now(UTC).date()
        start = end - timedelta(days=370)
        try:
            provider = YahooHistoryProvider()
            MarketDataService(
                self.session,
                provider,
                sleep=lambda _seconds: None,
            ).ingest(
                [ticker],
                start,
                end,
                max_securities=1,
                max_window_days=400,
                max_attempts=1,
                pause_seconds=0,
            )
        except (ProviderError, ValueError) as exc:
            logger.warning(
                "history_fill_failed",
                extra={"ticker": ticker, "error": str(exc)},
            )


_NEWS_NOTE = (
    "Headlines and photos come from the configured news provider for "
    "open positions. A written summary is shown only when that provider "
    "sends one."
)


def _parse_items(raw: list[dict]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            items.append(NewsItem.model_validate(item))
        except ValidationError:
            continue
    return items


def _bar_freshness(timestamp: datetime | None) -> tuple[str, bool]:
    """A stored bar is historical. Age uses sessions, not a live-quote clock."""
    if timestamp is None:
        return "unavailable", False
    stale = bar_is_stale(
        timestamp.date(),
        datetime.now(UTC).date(),
        after_business_days=settings.history_stale_after_business_days,
    )
    return "historical", stale
