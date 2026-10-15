from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_learning_service
from app.schemas.learning import ExplainIn, ExplainOut, LearnCatalog, LearnPage
from app.services.learning_service import LearningService

router = APIRouter(prefix="/learn", tags=["learning"])


@router.post("/explain", response_model=ExplainOut)
def explain_text(
    body: ExplainIn,
    service: LearningService = Depends(get_learning_service),
) -> ExplainOut:
    return service.explain(
        body.text, portfolio_id=body.portfolio_id, ticker=body.ticker
    )


@router.get("", response_model=LearnCatalog)
def list_terms(
    service: LearningService = Depends(get_learning_service),
) -> LearnCatalog:
    return service.catalog()


@router.get("/{slug}", response_model=LearnPage)
def get_term(
    slug: str,
    portfolio_id: UUID | None = None,
    ticker: str | None = None,
    service: LearningService = Depends(get_learning_service),
) -> LearnPage:
    return service.page(slug, portfolio_id=portfolio_id, ticker=ticker)
