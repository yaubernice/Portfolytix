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
    CRITERIA_FIELDS,
    ScreenApplied,
    ScreenHit,
    ScreenRequest,
    ScreenResponse,
)

SCREENING_CACHE_SCHEMA = "v4"


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
            **{name: getattr(payload, name) for name in CRITERIA_FIELDS}
        )
        rows, total = self.fundamentals.screen(
            filters,
            limit=payload.limit,
            offset=payload.offset,
            sort_by=payload.sort_by,
            sort_direction=payload.sort_direction,
        )
        response = ScreenResponse(  # return the response object to the API layer
            items=[_hit(security, row) for security, row in rows],
            total=total,
            limit=payload.limit,
            offset=payload.offset,
            applied=ScreenApplied.model_validate(
                # include the applied filters in the response
                payload.model_dump(exclude={"limit", "offset"})
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


def _hit(security: Security, row: Fundamental | None) -> ScreenHit:
    # Transform SQLAlchemy rows into an API response object.
    # A listing with no snapshot keeps its identity and leaves ratios empty.
    return ScreenHit(
        security_id=security.id,
        ticker=security.ticker,
        name=security.name,
        exchange=security.exchange,
        sector=security.sector,
        industry=security.industry,
        asset_type=security.asset_type,
        currency=security.currency,
        as_of=None if row is None else row.as_of,
        roe=None if row is None else row.roe,
        pe_ratio=None if row is None else row.pe_ratio,
        revenue_growth=None if row is None else row.revenue_growth,
        market_cap=None if row is None else row.market_cap,
        eps=None if row is None else row.eps,
        revenue=None if row is None else row.revenue,
        profit_margin=None if row is None else row.profit_margin,
        dividend_yield=None if row is None else row.dividend_yield,
        beta=None if row is None else row.beta,
        ebitda=None if row is None else row.ebitda,
        shares_outstanding=None if row is None else row.shares_outstanding,
        price_to_book=None if row is None else row.price_to_book,
        price_to_sales=None if row is None else row.price_to_sales,
        roa=None if row is None else row.roa,
        earnings_growth=None if row is None else row.earnings_growth,
        provider=None if row is None else row.provider,
    )
