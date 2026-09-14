from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
