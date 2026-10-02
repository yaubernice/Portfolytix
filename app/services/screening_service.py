import hashlib
import json

from sqlalchemy.orm import Session

from app.core.cache import CacheBackend, NullCache
from app.core.config import settings
from app.db.models import Fundamental, Security
from app.repositories.fundamental_repository import (
    FundamentalRepository,
    ScreenFilters,
)
from app.schemas.screening import (
    ScreenApplied,
    ScreenHit,
    ScreenRequest,
    ScreenResponse,
)

SCREENING_CACHE_SCHEMA = "v1"


class ScreeningService:
    """Translate a structured screen into a parameterized query. No raw SQL."""

    def __init__(
        self,
        session: Session,
        cache: CacheBackend | None = None,
    ) -> None:
        self.fundamentals = FundamentalRepository(session)
        self.cache = cache or NullCache()

    def screen(self, payload: ScreenRequest) -> ScreenResponse:
        # The API layer has already validated this request object.
        cache_key = self._cache_key(payload)
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict):
            return ScreenResponse.model_validate(cached)

        filters = ScreenFilters(
            roe_min=payload.roe_min,
            roe_max=payload.roe_max,
            pe_min=payload.pe_min,
            pe_max=payload.pe_max,
            revenue_growth_min=payload.revenue_growth_min,
            revenue_growth_max=payload.revenue_growth_max,
            market_cap_min=payload.market_cap_min,
            market_cap_max=payload.market_cap_max,
            sector=payload.sector,
            exchange=payload.exchange,
        )
        rows, total = self.fundamentals.screen(
            filters,
            limit=payload.limit,
            offset=payload.offset,
        )
        response = ScreenResponse( #return the response object to the API layer
            items=[_hit(security, row) for security, row in rows],
            total=total,
            limit=payload.limit,
            offset=payload.offset,
            applied=ScreenApplied( #include the applied filters in the response
                roe_min=payload.roe_min,
                roe_max=payload.roe_max,
                pe_min=payload.pe_min,
                pe_max=payload.pe_max,
                revenue_growth_min=payload.revenue_growth_min,
                revenue_growth_max=payload.revenue_growth_max,
                market_cap_min=payload.market_cap_min,
                market_cap_max=payload.market_cap_max,
                sector=payload.sector,
                exchange=payload.exchange,
            ),
        )
        self.cache.set_json(
            cache_key,
            response.model_dump(mode="json"),
            settings.screening_cache_ttl_seconds,
        )
        return response

    def _cache_key(self, payload: ScreenRequest) -> str:
        version = self.cache.get_version("fundamentals")
        canonical = json.dumps(
            payload.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"screen:{SCREENING_CACHE_SCHEMA}:fundamentals-v{version}:{digest}"


def _hit(security: Security, row: Fundamental) -> ScreenHit:
    # Transform SQLAlchemy rows into an API response object.
    return ScreenHit(
        security_id=security.id,
        ticker=security.ticker,
        name=security.name,
        exchange=security.exchange,
        sector=security.sector,
        currency=security.currency,
        as_of=row.as_of,
        roe=row.roe,
        pe_ratio=row.pe_ratio,
        revenue_growth=row.revenue_growth,
        market_cap=row.market_cap,
    )
