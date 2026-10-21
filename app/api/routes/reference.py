from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_current_user,
    get_position_service,
    get_reference_service,
)
from app.db.models import User
from app.schemas.market import (
    HistoricalFreshness,
    NewsReadIn,
    NewsReadOut,
    NewsResponse,
    PortfolioNewsResponse,
    SecurityProfile,
)
from app.schemas.security import SecurityOut, SecurityPage
from app.services.position_service import PositionService
from app.services.reference_service import ReferenceService

router = APIRouter(tags=["reference"])


@router.get("/securities", response_model=SecurityPage)
def list_securities(
    exchange: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    asset_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> SecurityPage:
    return service.search(
        q=None,
        exchange=exchange,
        country=country,
        sector=sector,
        asset_type=asset_type,
        limit=limit,
        offset=offset,
    )


@router.get("/securities/search", response_model=SecurityPage)
def search_securities(
    q: str | None = Query(default=None, max_length=80),
    exchange: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    asset_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> SecurityPage:
    return service.search(
        q=q,
        exchange=exchange,
        country=country,
        sector=sector,
        asset_type=asset_type,
        limit=limit,
        offset=offset,
    )


@router.get("/securities/id/{security_id}/news", response_model=NewsResponse)
def security_news_by_id(
    security_id: UUID,
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> NewsResponse:
    """Cached headlines for one security. The simulator does not invent any."""
    return service.news_for(security_id)


@router.get("/securities/id/{security_id}", response_model=SecurityOut)
def get_security(
    security_id: UUID,
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> SecurityOut:
    """Universe row by id. ``/securities/{ticker}`` remains the price profile."""
    return service.get(security_id)


@router.get("/securities/{ticker}/freshness", response_model=HistoricalFreshness)
def security_freshness(
    ticker: str,
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> HistoricalFreshness:
    """Latest stored daily bar. Live quotes stay on ``/quotes``."""
    return service.historical_freshness(ticker)


@router.get("/securities/{ticker}", response_model=SecurityProfile)
def security_profile(
    ticker: str,
    period: Literal["1D", "1W", "1M", "3M", "1Y", "MAX"] | None = None,
    history_limit: int = Query(default=90, ge=1, le=5000),
    ensure_history: bool = False,
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> SecurityProfile:
    return service.profile(
        ticker,
        history_period=period,
        price_limit=history_limit,
        ensure_history=ensure_history,
    )


@router.get(
    "/portfolios/{portfolio_id}/news",
    response_model=PortfolioNewsResponse,
)
def portfolio_news(
    portfolio_id: UUID,
    _user: User = Depends(get_current_user),
    positions: PositionService = Depends(get_position_service),
    service: ReferenceService = Depends(get_reference_service),
) -> PortfolioNewsResponse:
    """Headlines for open positions. Another user's portfolio is 404."""
    rows = positions.list_positions(portfolio_id).positions
    held = [row for row in rows if row.quantity > 0]
    held.sort(key=lambda row: (-(row.weight or 0), row.ticker))
    return service.news_for_holdings(
        portfolio_id,
        [row.ticker for row in held],
    )


@router.post("/news/read", response_model=NewsReadOut)
def read_news(
    body: NewsReadIn,
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> NewsReadOut:
    """What one opened story is about. The article text is not returned."""
    return service.read_story(body.url, body.headline)


@router.get("/news", response_model=NewsResponse)
def security_news(
    ticker: str = Query(min_length=1, max_length=16),
    _user: User = Depends(get_current_user),
    service: ReferenceService = Depends(get_reference_service),
) -> NewsResponse:
    return service.news(ticker)
