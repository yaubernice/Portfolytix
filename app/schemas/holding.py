from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DecimalStr


class HoldingOut(BaseModel):
    """Current position derived from BUY minus SELL. Not a stored table."""

    model_config = ConfigDict(from_attributes=True)

    security_id: UUID
    ticker: str
    quantity: DecimalStr = Field(description="Net shares: sum(BUY) - sum(SELL)")
