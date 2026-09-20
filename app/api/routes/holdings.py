from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_portfolio_service
from app.schemas.holding import HoldingOut
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["holdings"])

@router.get("", response_model=list[HoldingOut])
def list_holdings(
    portfolio_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[HoldingOut]:
    return service.list_holdings(portfolio_id)
