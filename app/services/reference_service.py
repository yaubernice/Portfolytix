from __future__ import annotations

from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.db.models import ASSET_TYPES, Fundamental, Price, Security
from app.quotes.store import QuoteStore
from app.repositories.price_repository import PriceRepository
from app.repositories.security_repository import SecurityQuery, SecurityRepository
from app.schemas.market import (
    HistoricalFreshness,
    NewsItem,
    NewsResponse,
    PriceBarOut,
    SecurityProfile,
)
from app.schemas.security import SecurityOut, SecurityPage


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
    ) -> SecurityProfile:
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker.upper()} not found")
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
        timeliness = "historical" if latest is not None else "unavailable"
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
            )
        return HistoricalFreshness(
            security_id=security.id,
            ticker=security.ticker,
            latest_bar=latest.timestamp.date(),
            source=latest.source,
            last_successful_update=updated,
            timeliness="historical",
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

    def _news(self, security: Security) -> NewsResponse:
        symbol = security.ticker
        raw = self.quotes.get_news(symbol)
        if not raw:
            return NewsResponse(
                ticker=symbol,
                security_id=security.id,
                source="none",
                provider="none",
                items=[],
            )
        items = [
            NewsItem.model_validate(item)
            for item in raw
            if isinstance(item, dict)
        ]
        source = items[0].source if items else "none"
        provider = items[0].provider if items and items[0].provider else "none"
        return NewsResponse(
            ticker=symbol,
            security_id=security.id,
            source=source,
            provider=provider,
            items=items,
        )
