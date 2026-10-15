from fastapi import APIRouter, Depends

from app.core.cache import CacheBackend, get_cache
from app.schemas.cache import CacheStatsOut

router = APIRouter(prefix="/cache", tags=["cache"])


# Get the cache implementation through FastAPI dependency injection.
@router.get("/stats", response_model=CacheStatsOut)
def get_cache_stats(
    cache: CacheBackend = Depends(get_cache),
) -> CacheStatsOut:
    # Ask the cache for statistics and convert them to the API schema.
    return CacheStatsOut.model_validate(cache.stats())
