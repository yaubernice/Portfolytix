from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SecurityOut(BaseModel):
    """One row in the security universe. Ticker is not the primary identity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticker: str
    name: str
    exchange: str
    mic: str | None = None
    sector: str
    industry: str | None = None
    country: str | None = None
    currency: str
    asset_type: str
    provider: str
    provider_symbol: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SecurityPage(BaseModel):
    items: list[SecurityOut]
    total: int
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
