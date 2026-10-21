from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.ai.local import LocalAssistant
from app.ai.provider import AssistantModel
from app.api.dependencies import get_assistant_model, get_research_service
from app.schemas.research import (
    AttentionResponse,
    FlagCreate,
    FlagOut,
    RecommendationResponse,
)
from app.services.research_service import ResearchService

router = APIRouter(tags=["research"])


@router.get(
    "/portfolios/{portfolio_id}/recommendations",
    response_model=RecommendationResponse,
)
def recommendations(
    portfolio_id: UUID,
    service: ResearchService = Depends(get_research_service),
    model: AssistantModel = Depends(get_assistant_model),
) -> RecommendationResponse:
    result = service.recommendations(portfolio_id)
    notes = [
        {"ticker": item.ticker, "points": item.points} for item in result.items
    ]
    if notes:
        try:
            result.commentary = model.comment_on_ideas(notes)
            result.commentary_source = model.interpretation_source
        except Exception:
            local = LocalAssistant()
            result.commentary = local.comment_on_ideas(notes)
            result.commentary_source = local.interpretation_source
    return result


@router.get(
    "/portfolios/{portfolio_id}/attention",
    response_model=AttentionResponse,
)
def attention(
    portfolio_id: UUID,
    service: ResearchService = Depends(get_research_service),
) -> AttentionResponse:
    return service.attention(portfolio_id)


@router.get("/flags", response_model=list[FlagOut])
def list_flags(
    service: ResearchService = Depends(get_research_service),
) -> list[FlagOut]:
    return service.list_flags()


@router.post("/flags", response_model=FlagOut, status_code=status.HTTP_201_CREATED)
def create_flag(
    payload: FlagCreate,
    service: ResearchService = Depends(get_research_service),
) -> FlagOut:
    return service.create_flag(payload)


@router.delete("/flags/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flag(
    flag_id: UUID,
    service: ResearchService = Depends(get_research_service),
) -> Response:
    service.delete_flag(flag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
