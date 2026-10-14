from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, OptionalDecimalStr


class AnalyticsAssumptions(BaseModel):
    method: str
    price_field: str
    risk_free_rate_annual: DecimalStr
    trading_days_per_year: int
    return_frequency: str
    volatility: str
    sharpe: str
    max_drawdown: str
    cash_treatment: str
    disclaimer: str


class SeriesPoint(BaseModel):
    date: date
    value: DecimalStr
    cash_flow: DecimalStr
    daily_pl: OptionalDecimalStr = None
    daily_return: OptionalDecimalStr = None
    cumulative_return: OptionalDecimalStr = None
    drawdown: DecimalStr = Decimal("0")


class AllocationOut(BaseModel):
    security_id: UUID
    ticker: str
    quantity: DecimalStr
    price: DecimalStr
    market_value: DecimalStr
    weight: DecimalStr = Field(description="Market value / portfolio market value")


class AnalyticsOut(BaseModel):
    portfolio_id: UUID
    start_date: date | None
    end_date: date | None
    observation_count: int
    total_return: OptionalDecimalStr = Field(
        default=None,
        description="Time-weighted geometric return over the sample, not annualized",
    )
    annualized_return: OptionalDecimalStr = None
    volatility: OptionalDecimalStr = Field(
        default=None,
        description="Annualized sample stdev of daily TWR: σ_daily × √252",
    )
    sharpe_ratio: OptionalDecimalStr = None
    max_drawdown: OptionalDecimalStr = Field(
        default=None,
        description="Worst peak-to-trough decline of the TWR wealth index (≤ 0)",
    )
    allocation: list[AllocationOut]
    series: list[SeriesPoint]
    assumptions: AnalyticsAssumptions
