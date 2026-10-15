from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Price
from app.quotes.models import LiveQuote
from app.quotes.store import QuoteStore
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.position import (
    PositionContribution,
    PositionOut,
    PositionsResponse,
    PriceFreshness,
)
from app.services.positions import AverageCost, CostFill, average_cost_positions


class PositionService:
    """Holdings plus average cost, marked with the live quote or last close."""

    def __init__(
        self,
        session: Session,
        user_id: UUID,
        quotes: QuoteStore,
    ) -> None:
        self.user_id = user_id
        self.session = session
        self.portfolios = PortfolioRepository(session)
        self.transactions = TransactionRepository(session)
        self.quotes = quotes

    def list_positions(self, portfolio_id: UUID) -> PositionsResponse:
        if self.portfolios.get_owned(portfolio_id, self.user_id) is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        fills = [
            CostFill(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
                price=row.price,
            )
            for row in self.transactions.list_for_portfolio(portfolio_id)
        ]
        costs = average_cost_positions(fills)
        live = {quote.ticker: quote for quote in self.quotes.snapshot()}
        positions = [self._position(row, live.get(row.ticker)) for row in costs]
        total = sum(
            (row.market_value for row in positions if row.market_value is not None),
            Decimal("0"),
        )
        if total > 0:
            weighted: list[PositionOut] = []
            for row in positions:
                weight = (
                    row.market_value / total if row.market_value is not None else None
                )
                weighted.append(row.model_copy(update={"weight": weight}))
            positions = weighted
        day_values = [row.day_pl for row in positions if row.day_pl is not None]
        day_pl = sum(day_values, Decimal("0")) if day_values else None
        cost_values = [
            row.cost_basis for row in positions if row.cost_basis is not None
        ]
        cost_basis = sum(cost_values, Decimal("0")) if cost_values else None
        unrealized_values = [
            row.unrealized_pl for row in positions if row.unrealized_pl is not None
        ]
        unrealized_pl = (
            sum(unrealized_values, Decimal("0")) if unrealized_values else None
        )
        contributors = sorted(
            (row for row in positions if row.day_pl is not None and row.day_pl > 0),
            key=lambda row: row.day_pl or Decimal("0"),
            reverse=True,
        )
        detractors = sorted(
            (row for row in positions if row.day_pl is not None and row.day_pl < 0),
            key=lambda row: row.day_pl or Decimal("0"),
        )
        market_value = total if positions else None
        return PositionsResponse(
            portfolio_id=portfolio_id,
            cost_basis=cost_basis,
            market_value=market_value,
            unrealized_pl=unrealized_pl,
            day_pl=day_pl,
            top_contributors=[_contribution(row) for row in contributors[:3]],
            top_detractors=[_contribution(row) for row in detractors[:3]],
            positions=positions,
        )

    def _position(self, row: AverageCost, quote: LiveQuote | None) -> PositionOut:
        previous = quote.previous_close if quote is not None else None
        price = quote.price if quote is not None else None
        source = quote.source if quote is not None else "database"
        timeliness = quote.timeliness if quote is not None else "unavailable"
        bar_at = None
        if price is None:
            closes = self._recent_bars(row.security_id)
            if closes:
                price, bar_at = closes[-1]
                source = "database"
                timeliness = "historical"
                if previous is None and len(closes) > 1:
                    previous = closes[-2][0]
        market_value = price * row.quantity if price is not None else None
        cost_basis = (
            row.avg_cost * row.quantity if row.avg_cost is not None else None
        )
        unrealized = (
            (price - row.avg_cost) * row.quantity
            if price is not None and row.avg_cost is not None
            else None
        )
        day_pl = (
            (price - previous) * row.quantity
            if price is not None and previous is not None
            else None
        )
        return PositionOut(
            security_id=row.security_id,
            ticker=row.ticker,
            quantity=row.quantity,
            average_cost=row.avg_cost,
            avg_cost=row.avg_cost,
            cost_basis=cost_basis,
            current_price=price,
            price=price,
            previous_close=previous,
            market_value=market_value,
            unrealized_pl=unrealized,
            day_pl=day_pl,
            price_source=source,
            price_timeliness=timeliness,
            quote_provider_timestamp=(
                quote.provider_timestamp if quote is not None else None
            ),
            quote_received_at=quote.received_at if quote is not None else None,
            quote_age_seconds=quote.age_seconds if quote is not None else None,
            freshness=PriceFreshness(
                source=source,
                timeliness=timeliness,
                as_of=(
                    quote.provider_timestamp if quote is not None else bar_at
                ),
                received_at=quote.received_at if quote is not None else None,
                age_seconds=quote.age_seconds if quote is not None else None,
            ),
        )

    def _recent_bars(self, security_id: UUID) -> list[tuple[Decimal, datetime]]:
        statement = (
            select(Price.adjusted_close, Price.timestamp)
            .where(Price.security_id == security_id)
            .order_by(Price.timestamp.desc())
            .limit(2)
        )
        rows = list(self.session.execute(statement))
        rows.reverse()
        return [(row[0], row[1]) for row in rows]


def _contribution(row: PositionOut) -> PositionContribution:
    assert row.day_pl is not None
    return PositionContribution(
        ticker=row.ticker,
        day_pl=row.day_pl,
        market_value=row.market_value,
        weight=row.weight,
    )
