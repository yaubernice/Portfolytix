from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_analytics_service
from app.schemas.analytics import AnalyticsOut
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/portfolios/{portfolio_id}/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsOut)
def get_analytics(
    portfolio_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOut:
    return service.get_analytics(portfolio_id)
