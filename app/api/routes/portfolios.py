from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_portfolio_service
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioDetail,
    PortfolioSummary,
    PortfolioUpdate,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.post("", response_model=PortfolioSummary, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioSummary:
    return service.create_portfolio(payload)


@router.get("", response_model=list[PortfolioSummary])
def list_portfolios(
    user_id: UUID = Query(..., description="Owner whose portfolios to list"),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[PortfolioSummary]:
    return service.list_portfolios(user_id)


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
def get_portfolio(
    portfolio_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    return service.get_portfolio(portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioDetail)
def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    return service.update_portfolio(portfolio_id, payload)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> Response:
    service.delete_portfolio(portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
