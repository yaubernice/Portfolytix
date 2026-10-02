from datetime import date
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DecimalStr, OptionalDecimalStr


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
    sector: str | None = None
    exchange: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("sector", "exchange")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped.lower() if stripped else None

    @model_validator(mode="after")
    def _min_lte_max(self) -> Self: #check if the min is less than the max
        pairs: tuple[tuple[str, Decimal | None, Decimal | None], ...] = (
            ("roe", self.roe_min, self.roe_max),
            ("pe", self.pe_min, self.pe_max),
            ("revenue_growth", self.revenue_growth_min, self.revenue_growth_max),
            ("market_cap", self.market_cap_min, self.market_cap_max),
        )
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
    currency: str
    as_of: date #date is a datetime.date object
    roe: DecimalStr
    pe_ratio: DecimalStr
    revenue_growth: DecimalStr
    market_cap: DecimalStr


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
    sector: str | None = None
    exchange: str | None = None


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
