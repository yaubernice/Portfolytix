from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JobRunOut(BaseModel):
    id: UUID
    job_name: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    window_start: date | None
    window_end: date | None
    provider: str | None
    fetched: int
    accepted: int
    upserted: int
    skipped_invalid: int
    failed_tickers: list[str]
    error: str | None

    model_config = {"from_attributes": True}


class JobRunListOut(BaseModel):
    items: list[JobRunOut]
    count: int = Field(description="Number of rows in this response, not the table")
