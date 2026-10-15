from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import DecimalStr, OptionalDecimalStr


class FlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["security", "sector"]
    security_id: UUID | None = None
    sector: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def match_target(self) -> Self:
        if self.target_type == "security":
            if self.security_id is None or self.sector is not None:
                raise ValueError("A security flag needs security_id only")
        elif self.sector is None or self.security_id is not None:
            raise ValueError("A sector flag needs sector only")
        if self.sector is not None:
            self.sector = " ".join(self.sector.split())
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class FlagOut(BaseModel):
    id: UUID
    target_type: Literal["security", "sector"]
    security_id: UUID | None = None
    ticker: str | None = None
    name: str | None = None
    sector: str | None = None
    note: str | None = None
    created_at: datetime


class AttentionStock(BaseModel):
    security_id: UUID
    ticker: str
    name: str
    sector: str
    day_pl: DecimalStr
    weight: OptionalDecimalStr = None


class AttentionArea(BaseModel):
    sector: str
    day_pl: DecimalStr
    weight: OptionalDecimalStr = None


class AttentionResponse(BaseModel):
    portfolio_id: UUID
    stocks: list[AttentionStock]
    areas: list[AttentionArea]


class Recommendation(BaseModel):
    security_id: UUID
    ticker: str
    name: str
    sector: str
    roe: OptionalDecimalStr = None
    pe_ratio: OptionalDecimalStr = None
    reason: str


class RecommendationResponse(BaseModel):
    portfolio_id: UUID
    disclaimer: str
    items: list[Recommendation]
