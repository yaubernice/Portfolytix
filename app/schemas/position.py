from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, OptionalDecimalStr


class PriceFreshness(BaseModel):
    source: str
    timeliness: str
    as_of: datetime | None = None
    received_at: datetime | None = None
    age_seconds: float | None = None


class PositionOut(BaseModel):
    security_id: UUID
    ticker: str
    quantity: DecimalStr
    average_cost: OptionalDecimalStr = None
    avg_cost: OptionalDecimalStr = None
    cost_basis: OptionalDecimalStr = None
    current_price: OptionalDecimalStr = None
    price: OptionalDecimalStr = None
    previous_close: OptionalDecimalStr = None
    market_value: OptionalDecimalStr = None
    unrealized_pl: OptionalDecimalStr = None
    day_pl: OptionalDecimalStr = None
    weight: OptionalDecimalStr = None
    price_source: str
    price_timeliness: str = "unavailable"
    quote_provider_timestamp: datetime | None = None
    quote_received_at: datetime | None = None
    quote_age_seconds: float | None = None
    freshness: PriceFreshness


class PositionContribution(BaseModel):
    ticker: str
    day_pl: DecimalStr
    market_value: OptionalDecimalStr = None
    weight: OptionalDecimalStr = None


class PositionsResponse(BaseModel):
    portfolio_id: UUID
    cost_basis: OptionalDecimalStr = None
    market_value: OptionalDecimalStr = None
    unrealized_pl: OptionalDecimalStr = None
    day_pl: OptionalDecimalStr = None
    top_contributors: list[PositionContribution] = Field(default_factory=list)
    top_detractors: list[PositionContribution] = Field(default_factory=list)
    positions: list[PositionOut]
