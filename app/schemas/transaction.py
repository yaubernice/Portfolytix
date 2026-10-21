from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.transaction import TransactionType
from app.schemas.common import PositiveDecimal


class TransactionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    transaction_type: TransactionType
    quantity: PositiveDecimal
    price: PositiveDecimal
    timestamp: datetime | None = Field(
        default=None,
        description="Fill time. Defaults to now (UTC) when omitted.",
    )

    @field_validator("quantity")
    @classmethod
    def whole_shares(cls, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise ValueError("Quantity must be a whole number of shares")
        return value


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    security_id: UUID
    ticker: str
    transaction_type: TransactionType
    quantity: PositiveDecimal
    price: PositiveDecimal
    timestamp: datetime
    created_at: datetime
