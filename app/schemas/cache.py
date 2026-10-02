from pydantic import BaseModel, Field


class CacheStatsOut(BaseModel):
    hits: int
    misses: int
    sets: int
    invalidations: int
    errors: int
    requests: int
    hit_rate: float = Field(ge=0, le=1)
