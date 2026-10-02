from fastapi import APIRouter, Depends

from app.core.cache import CacheBackend, get_cache
from app.schemas.cache import CacheStatsOut

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", response_model=CacheStatsOut)
def get_cache_stats(
    cache: CacheBackend = Depends(get_cache),
) -> CacheStatsOut:
    return CacheStatsOut.model_validate(cache.stats())
