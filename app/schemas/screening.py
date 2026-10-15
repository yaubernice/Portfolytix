from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DecimalStr, OptionalDecimalStr

# Prefixes for min/max pairs. Text filters are exact labels.
RANGE_FIELDS = (
    "roe",
    "pe",
    "revenue_growth",
    "market_cap",
    "eps",
    "revenue",
    "profit_margin",
    "dividend_yield",
    "beta",
    "ebitda",
    "price_to_book",
    "price_to_sales",
    "roa",
    "earnings_growth",
)

CRITERIA_FIELDS = tuple(
    f"{name}_{bound}" for name in RANGE_FIELDS for bound in ("min", "max")
) + ("sector", "industry", "exchange")


class ScreenSort(StrEnum):
    TICKER = "ticker"
    ROE = "roe"
    PE_RATIO = "pe_ratio"
    REVENUE_GROWTH = "revenue_growth"
    MARKET_CAP = "market_cap"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ScreenRequest(BaseModel):
    """Structured screen. Unknown fields are rejected (no SQL injection path)."""

    # Only declared fields are accepted; unknown input gets a 422.
    model_config = ConfigDict(extra="forbid")

    # OptionalDecimalStr parses Decimal and serializes it as a JSON string.
    roe_min: OptionalDecimalStr = None
    roe_max: OptionalDecimalStr = None
    pe_min: OptionalDecimalStr = None
    pe_max: OptionalDecimalStr = None
    revenue_growth_min: OptionalDecimalStr = None
    revenue_growth_max: OptionalDecimalStr = None
    market_cap_min: OptionalDecimalStr = Field(
        default=None,
        description="USD, not billions. 10000000000 = $10B.",
    )
    market_cap_max: OptionalDecimalStr = None
    eps_min: OptionalDecimalStr = None
    eps_max: OptionalDecimalStr = None
    revenue_min: OptionalDecimalStr = None
    revenue_max: OptionalDecimalStr = None
    profit_margin_min: OptionalDecimalStr = None
    profit_margin_max: OptionalDecimalStr = None
    dividend_yield_min: OptionalDecimalStr = None
    dividend_yield_max: OptionalDecimalStr = None
    beta_min: OptionalDecimalStr = None
    beta_max: OptionalDecimalStr = None
    ebitda_min: OptionalDecimalStr = None
    ebitda_max: OptionalDecimalStr = None
    price_to_book_min: OptionalDecimalStr = None
    price_to_book_max: OptionalDecimalStr = None
    price_to_sales_min: OptionalDecimalStr = None
    price_to_sales_max: OptionalDecimalStr = None
    roa_min: OptionalDecimalStr = None
    roa_max: OptionalDecimalStr = None
    earnings_growth_min: OptionalDecimalStr = None
    earnings_growth_max: OptionalDecimalStr = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    sort_by: ScreenSort = ScreenSort.TICKER
    sort_direction: SortDirection = SortDirection.ASC
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("sector", "industry", "exchange")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped.lower() if stripped else None

    @model_validator(mode="after")
    def _min_lte_max(self) -> Self: #check if the min is less than the max
        pairs = [
            (name, getattr(self, f"{name}_min"), getattr(self, f"{name}_max"))
            for name in RANGE_FIELDS
        ]
        for name, low, high in pairs:
            if low is not None and high is not None and low > high:
                raise ValueError(f"{name}_min must be <= {name}_max")
        if self.market_cap_min is not None and self.market_cap_min <= 0:
            raise ValueError("market_cap_min must be > 0")
        if self.market_cap_max is not None and self.market_cap_max <= 0:
            raise ValueError("market_cap_max must be > 0")
        return self


class ScreenHit(BaseModel): #database object is converted to a ScreenHit object
    security_id: UUID
    ticker: str
    name: str
    exchange: str
    sector: str
    industry: str | None = None
    currency: str
    as_of: date #date is a datetime.date object
    roe: DecimalStr
    pe_ratio: DecimalStr
    revenue_growth: DecimalStr
    market_cap: DecimalStr
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
    provider: str | None = None


class ScreenApplied(BaseModel):
    # Echo screening criteria only; limit/offset are pagination controls.
    roe_min: OptionalDecimalStr = None
    roe_max: OptionalDecimalStr = None
    pe_min: OptionalDecimalStr = None
    pe_max: OptionalDecimalStr = None
    revenue_growth_min: OptionalDecimalStr = None
    revenue_growth_max: OptionalDecimalStr = None
    market_cap_min: OptionalDecimalStr = None
    market_cap_max: OptionalDecimalStr = None
    eps_min: OptionalDecimalStr = None
    eps_max: OptionalDecimalStr = None
    revenue_min: OptionalDecimalStr = None
    revenue_max: OptionalDecimalStr = None
    profit_margin_min: OptionalDecimalStr = None
    profit_margin_max: OptionalDecimalStr = None
    dividend_yield_min: OptionalDecimalStr = None
    dividend_yield_max: OptionalDecimalStr = None
    beta_min: OptionalDecimalStr = None
    beta_max: OptionalDecimalStr = None
    ebitda_min: OptionalDecimalStr = None
    ebitda_max: OptionalDecimalStr = None
    price_to_book_min: OptionalDecimalStr = None
    price_to_book_max: OptionalDecimalStr = None
    price_to_sales_min: OptionalDecimalStr = None
    price_to_sales_max: OptionalDecimalStr = None
    roa_min: OptionalDecimalStr = None
    roa_max: OptionalDecimalStr = None
    earnings_growth_min: OptionalDecimalStr = None
    earnings_growth_max: OptionalDecimalStr = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    sort_by: ScreenSort = ScreenSort.TICKER
    sort_direction: SortDirection = SortDirection.ASC


class NaturalScreenRequest(BaseModel):
    """English screen. The parser must emit ScreenRequest before any query."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    sort_by: ScreenSort = ScreenSort.TICKER
    sort_direction: SortDirection = SortDirection.ASC
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class NaturalScreenResponse(BaseModel):
    query: str
    parser: str
    items: list[ScreenHit]
    total: int
    limit: int
    offset: int
    applied: ScreenApplied
    disclaimer: str


class ScreenResponse(BaseModel):
    items: list[ScreenHit]
    total: int
    limit: int
    offset: int
    applied: ScreenApplied
    disclaimer: str = (
        "Synthetic or stored fundamentals, not investment advice. "
        "Ratios are decimals (0.15 = 15%). P/E is a multiple. "
        "market_cap is USD."
    )
