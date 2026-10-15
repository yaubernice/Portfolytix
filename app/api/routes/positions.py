from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_position_service
from app.schemas.position import PositionsResponse
from app.services.position_service import PositionService

router = APIRouter(prefix="/portfolios/{portfolio_id}/positions", tags=["positions"])


@router.get("", response_model=PositionsResponse)
def list_positions(
    portfolio_id: UUID,
    service: PositionService = Depends(get_position_service),
) -> PositionsResponse:
    return service.list_positions(portfolio_id)
