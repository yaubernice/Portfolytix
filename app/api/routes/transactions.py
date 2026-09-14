from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_portfolio_service
from app.schemas.transaction import TransactionCreate, TransactionOut
from app.services.portfolio_service import PortfolioService

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/transactions",
    tags=["transactions"],
)


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    portfolio_id: UUID,
    payload: TransactionCreate,
    service: PortfolioService = Depends(get_portfolio_service),
) -> TransactionOut:
    return service.add_transaction(portfolio_id, payload)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[TransactionOut]:
    return service.list_transactions(portfolio_id)
