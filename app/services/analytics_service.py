from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.cache import CacheBackend, NullCache
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Transaction
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.price_repository import PriceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.analytics import (
    AllocationOut,
    AnalyticsAssumptions,
    AnalyticsOut,
    SeriesPoint,
)
from app.services.analytics import (
    CloseBar,
    allocation,
    annualized_return,
    annualized_volatility,
    build_value_series,
    daily_returns_of,
    fill_from_transaction,
    max_drawdown,
    sharpe_ratio,
    total_return,
)
from app.services.holdings import PositionLeg, aggregate_positions

ANALYTICS_CACHE_SCHEMA = "v1"


class AnalyticsService:
    def __init__(
        self,
        session: Session,
        cache: CacheBackend | None = None,
    ) -> None:
        self.portfolios = PortfolioRepository(session)
        self.transactions = TransactionRepository(session)
        self.prices = PriceRepository(session)
        self.cache = cache or NullCache()

    def get_analytics(self, portfolio_id: UUID) -> AnalyticsOut:
        if self.portfolios.get(portfolio_id) is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")

        cache_key = self._cache_key(portfolio_id)
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict):
            return AnalyticsOut.model_validate(cached)

        result = self._calculate(portfolio_id)
        self.cache.set_json(
            cache_key,
            result.model_dump(mode="json"),
            settings.analytics_cache_ttl_seconds,
        )
        return result

    def _calculate(self, portfolio_id: UUID) -> AnalyticsOut:
        rows = self.transactions.list_for_portfolio(portfolio_id)
        if not rows:
            raise ConflictError("Portfolio has no transactions")

        fills = [_fill(row) for row in rows]
        security_ids = list({fill.security_id for fill in fills})
        bars = [
            CloseBar(security_id=sid, on=_as_utc_date(ts), close=close)
            for sid, ts, close in self.prices.list_closes(security_ids)
        ]
        if not bars:
            raise ConflictError("No price history for portfolio holdings")

        points = build_value_series(fills, bars)
        returns = daily_returns_of(points)
        rf = settings.risk_free_rate
        periods = settings.trading_days_per_year

        holdings = aggregate_positions(
            [
                PositionLeg(
                    security_id=row.security_id,
                    ticker=row.security.ticker,
                    transaction_type=row.transaction_type,
                    quantity=row.quantity,
                )
                for row in rows
            ]
        )
        quantities = {item.security_id: item.quantity for item in holdings}
        tickers = {item.security_id: item.ticker for item in holdings}
        latest = _latest_marks(bars)
        alloc = allocation(quantities, tickers, latest)

        start = points[0].on if points else None
        end = points[-1].on if points else None
        return AnalyticsOut(
            portfolio_id=portfolio_id,
            start_date=start,
            end_date=end,
            observation_count=len(returns),
            total_return=total_return(returns) if returns else Decimal("0"),
            annualized_return=annualized_return(returns, periods),
            volatility=annualized_volatility(returns, periods),
            sharpe_ratio=sharpe_ratio(returns, rf, periods),
            max_drawdown=max_drawdown(returns) if returns else Decimal("0"),
            allocation=[
                AllocationOut(
                    security_id=line.security_id,
                    ticker=line.ticker,
                    quantity=line.quantity,
                    price=line.price,
                    market_value=line.market_value,
                    weight=line.weight,
                )
                for line in alloc
            ],
            series=[
                SeriesPoint(
                    date=point.on,
                    value=point.value,
                    cash_flow=point.cash_flow,
                    daily_return=point.daily_return,
                    cumulative_return=point.cumulative_return,
                )
                for point in points
            ],
            assumptions=_assumptions(rf, periods),
        )

    def _cache_key(self, portfolio_id: UUID) -> str:
        portfolio_version = self.cache.get_version(f"portfolio:{portfolio_id}")
        prices_version = self.cache.get_version("prices")
        return (
            f"portfolio:{portfolio_id}:analytics:{ANALYTICS_CACHE_SCHEMA}:"
            f"portfolio-v{portfolio_version}:prices-v{prices_version}"
        )


def _fill(row: Transaction):
    return fill_from_transaction( #row = SQLAlchemy Transaction object
        on=_as_utc_date(row.timestamp),
        security_id=row.security_id,
        ticker=row.security.ticker,
        transaction_type=row.transaction_type,
        quantity=row.quantity,
        price=row.price,
    )


def _as_utc_date(value: datetime) -> date: #convert datetime to date
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()


def _latest_marks(bars: list[CloseBar]) -> dict[UUID, Decimal]:
    latest: dict[UUID, Decimal] = {}
    for bar in bars:
        latest[bar.security_id] = bar.close
    return latest


def _assumptions(risk_free_rate: Decimal, periods: int) -> AnalyticsAssumptions:
    return AnalyticsAssumptions(
        method="time_weighted",
        price_field="adjusted_close",
        risk_free_rate_annual=risk_free_rate,
        trading_days_per_year=periods,
        return_frequency="daily",
        volatility="sample_stdev(daily_twr) * sqrt(trading_days_per_year)",
        sharpe="(mean(daily_twr) - rf/trading_days) / stdev(daily_twr)",
        max_drawdown="min(wealth / running_peak - 1) on TWR wealth index",
        cash_treatment=(
            "BUY is an external contribution, SELL is a withdrawal; "
            "no cash sleeve is modeled"
        ),
        disclaimer="Not investment advice. Teaching calculations only.",
    )
