from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class WatchlistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class WatchlistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    security_id: UUID


class WatchlistItemOut(BaseModel):
    id: UUID
    security_id: UUID
    ticker: str
    name: str
    exchange: str
    created_at: datetime


class WatchlistSummary(BaseModel):
    id: UUID
    name: str
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistPage(BaseModel):
    items: list[WatchlistSummary]
    total: int
    limit: int
    offset: int


class WatchlistDetail(WatchlistSummary):
    items: list[WatchlistItemOut]
    items_total: int
    items_limit: int
    items_offset: int
