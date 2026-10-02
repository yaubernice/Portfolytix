from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Fundamental, Security


# frozen makes values immutable; slots avoids one __dict__ per filter object.
@dataclass(frozen=True, slots=True)
class ScreenFilters:
    """Bound values only. Callers never pass SQL fragments."""

    roe_min: Decimal | None = None
    roe_max: Decimal | None = None
    pe_min: Decimal | None = None
    pe_max: Decimal | None = None
    revenue_growth_min: Decimal | None = None
    revenue_growth_max: Decimal | None = None
    market_cap_min: Decimal | None = None
    market_cap_max: Decimal | None = None
    sector: str | None = None
    exchange: str | None = None


class FundamentalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def screen(
        self,
        filters: ScreenFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Security, Fundamental]], int]:
        """Latest snapshot per security matching the structured filters.

        SQL is always parameterized (``Fundamental.roe >= :roe_min``).
        Unknown filter keys never reach this method.
        """
        base = (
            select(Security, Fundamental)
            # Connect each Fundamental to its Security identity.
            .join(Fundamental, Fundamental.security_id == Security.id)
        )
        # Each call returns a new Select; the original is not mutated.
        filtered = _apply_filters(base, filters)
        total = int(
            self.session.scalar(
                # Count matching companies before LIMIT / OFFSET.
                select(func.count()).select_from(filtered.subquery())
            )
            or 0
        )
        page = filtered.order_by(Security.ticker).limit(limit).offset(offset)
        # Rows contain company identity plus its current financial facts.
        rows = list(self.session.execute(page).all())
        return rows, total


def _apply_filters(
    # Result rows contain (Security, Fundamental).
    statement: Select[tuple[Security, Fundamental]],
    filters: ScreenFilters,
) -> Select[tuple[Security, Fundamental]]:
    if filters.roe_min is not None:
        # Add a bound WHERE clause; no user SQL is interpolated.
        statement = statement.where(Fundamental.roe >= filters.roe_min)
    if filters.roe_max is not None:
        statement = statement.where(Fundamental.roe <= filters.roe_max)
    if filters.pe_min is not None:
        statement = statement.where(Fundamental.pe_ratio >= filters.pe_min)
    if filters.pe_max is not None:
        statement = statement.where(Fundamental.pe_ratio <= filters.pe_max)
    if filters.revenue_growth_min is not None:
        statement = statement.where(
            Fundamental.revenue_growth >= filters.revenue_growth_min
        )
    if filters.revenue_growth_max is not None:
        statement = statement.where(
            Fundamental.revenue_growth <= filters.revenue_growth_max
        )
    if filters.market_cap_min is not None:
        statement = statement.where(Fundamental.market_cap >= filters.market_cap_min)
    if filters.market_cap_max is not None:
        statement = statement.where(Fundamental.market_cap <= filters.market_cap_max)
    if filters.sector is not None:
        # Compare normalized lower-case values.
        statement = statement.where(func.lower(Security.sector) == filters.sector)
    if filters.exchange is not None:
        statement = statement.where(func.lower(Security.exchange) == filters.exchange)
    return statement
