from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

from app.db.models import Fundamental, Security
from app.schemas.screening import ScreenSort, SortDirection


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
    eps_min: Decimal | None = None
    eps_max: Decimal | None = None
    revenue_min: Decimal | None = None
    revenue_max: Decimal | None = None
    profit_margin_min: Decimal | None = None
    profit_margin_max: Decimal | None = None
    dividend_yield_min: Decimal | None = None
    dividend_yield_max: Decimal | None = None
    beta_min: Decimal | None = None
    beta_max: Decimal | None = None
    ebitda_min: Decimal | None = None
    ebitda_max: Decimal | None = None
    price_to_book_min: Decimal | None = None
    price_to_book_max: Decimal | None = None
    price_to_sales_min: Decimal | None = None
    price_to_sales_max: Decimal | None = None
    roa_min: Decimal | None = None
    roa_max: Decimal | None = None
    earnings_growth_min: Decimal | None = None
    earnings_growth_max: Decimal | None = None
    sector: str | None = None
    industry: str | None = None
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
        sort_by: ScreenSort,
        sort_direction: SortDirection,
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
        sort_column = _SORT_COLUMNS[sort_by]
        order = (
            desc(sort_column)
            if sort_direction is SortDirection.DESC
            else asc(sort_column)
        )
        page = (
            filtered.order_by(
                order.nulls_last(),
                Security.ticker.asc(),
                Security.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        # Rows contain company identity plus its current financial facts.
        rows = list(self.session.execute(page).all())
        return rows, total


# Filter prefix → column. A new screen field is a schema entry plus one row here.
_RANGE_COLUMNS = (
    ("roe", Fundamental.roe),
    ("pe", Fundamental.pe_ratio),
    ("revenue_growth", Fundamental.revenue_growth),
    ("market_cap", Fundamental.market_cap),
    ("eps", Fundamental.eps),
    ("revenue", Fundamental.revenue),
    ("profit_margin", Fundamental.profit_margin),
    ("dividend_yield", Fundamental.dividend_yield),
    ("beta", Fundamental.beta),
    ("ebitda", Fundamental.ebitda),
    ("price_to_book", Fundamental.price_to_book),
    ("price_to_sales", Fundamental.price_to_sales),
    ("roa", Fundamental.roa),
    ("earnings_growth", Fundamental.earnings_growth),
)

_SORT_COLUMNS = {
    ScreenSort.TICKER: Security.ticker,
    ScreenSort.ROE: Fundamental.roe,
    ScreenSort.PE_RATIO: Fundamental.pe_ratio,
    ScreenSort.REVENUE_GROWTH: Fundamental.revenue_growth,
    ScreenSort.MARKET_CAP: Fundamental.market_cap,
}


def _apply_filters(
    # Result rows contain (Security, Fundamental).
    statement: Select[tuple[Security, Fundamental]],
    filters: ScreenFilters,
) -> Select[tuple[Security, Fundamental]]:
    for name, column in _RANGE_COLUMNS:
        low = getattr(filters, f"{name}_min")
        high = getattr(filters, f"{name}_max")
        if low is not None:
            # Add a bound WHERE clause; no user SQL is interpolated.
            # NULL fundamentals do not satisfy a comparison.
            statement = statement.where(column >= low)
        if high is not None:
            statement = statement.where(column <= high)
    if filters.sector is not None:
        # Compare normalized lower-case values.
        statement = statement.where(func.lower(Security.sector) == filters.sector)
    if filters.industry is not None:
        statement = statement.where(
            func.lower(Security.industry) == filters.industry
        )
    if filters.exchange is not None:
        statement = statement.where(func.lower(Security.exchange) == filters.exchange)
    return statement
