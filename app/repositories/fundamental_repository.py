from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, and_, asc, desc, func, or_, select
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
    asset_type: str | None = None
    search: str | None = None


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
    ) -> tuple[list[tuple[Security, Fundamental | None]], int]:
        """Latest snapshot per security matching the structured filters.

        SQL is always parameterized (``Fundamental.roe >= :roe_min``).
        Unknown filter keys never reach this method.
        A sector, asset type, or name with no ratio bound includes listings
        that have no fundamental snapshot. An empty screen stays limited to
        stored snapshots.
        """
        join = Fundamental.security_id == Security.id
        linked = (
            select(Security, Fundamental).outerjoin(Fundamental, join)
            if _listings_without_snapshots(filters)
            else select(Security, Fundamental).join(Fundamental, join)
        )
        # Benchmark placeholders are inactive and are not part of the universe.
        base = linked.where(
            Security.is_active.is_(True),
            ~Security.ticker.like("BENCH%"),
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
        statement = statement.where(func.lower(Security.industry) == filters.industry)
    if filters.exchange is not None:
        statement = statement.where(func.lower(Security.exchange) == filters.exchange)
    if filters.asset_type is not None:
        statement = statement.where(Security.asset_type == filters.asset_type)
    if filters.search is not None:
        statement = statement.where(_search_clause(filters.search))
    return statement


def _listings_without_snapshots(filters: ScreenFilters) -> bool:
    identity = any(
        getattr(filters, name) is not None
        for name in ("sector", "industry", "exchange", "asset_type", "search")
    )
    ratio = any(
        getattr(filters, f"{name}_min") is not None
        or getattr(filters, f"{name}_max") is not None
        for name, _column in _RANGE_COLUMNS
    )
    return identity and not ratio


def _search_clause(search: str):
    # "China" is a name, not a ticker. Funds that exclude China stay out.
    if search == "china":
        named = or_(
            Security.name.ilike("%china%", escape="\\"),
            Security.name.ilike("%chinese%", escape="\\"),
        )
        return and_(
            named,
            ~Security.name.ilike("%ex-china%", escape="\\"),
            ~Security.name.ilike("%ex china%", escape="\\"),
        )
    # A single ticker is exact, so VOO does not also return VOOB.
    # The same word can also be part of a company name.
    if " " not in search and re.fullmatch(r"[a-z0-9.]{1,8}", search):
        return or_(
            func.lower(Security.ticker) == search,
            Security.name.ilike(_like(search), escape="\\"),
        )
    return and_(
        *(
            or_(
                Security.ticker.ilike(_like(part), escape="\\"),
                Security.name.ilike(_like(part), escape="\\"),
            )
            for part in search.split()
        )
    )


def _like(part: str) -> str:
    escaped = part.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
