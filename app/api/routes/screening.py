from fastapi import APIRouter, Depends

from app.ai.provider import AssistantModel
from app.api.dependencies import get_assistant_model, get_screening_service
from app.schemas.screening import (
    NaturalScreenRequest,
    NaturalScreenResponse,
    ScreenRequest,
    ScreenResponse,
)
from app.services.assistant_service import natural_screen, screen_note
from app.services.screening_service import ScreeningService

router = APIRouter(prefix="/screen", tags=["screening"])


@router.post("", response_model=ScreenResponse)
def screen(
    payload: ScreenRequest,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreenResponse:
    return service.screen(payload)


@router.post("/natural", response_model=NaturalScreenResponse)
def screen_natural(
    payload: NaturalScreenRequest,
    service: ScreeningService = Depends(get_screening_service),
    model: AssistantModel = Depends(get_assistant_model),
) -> NaturalScreenResponse:
    parser, result = natural_screen(
        payload.query,
        limit=payload.limit,
        offset=payload.offset,
        sort_by=payload.sort_by,
        sort_direction=payload.sort_direction,
        screening=service,
        model=model,
    )
    note, note_source = (None, None)
    if payload.offset == 0:
        note, note_source = screen_note(payload.query, result, model)
    return NaturalScreenResponse(
        query=payload.query,
        parser=parser,
        items=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        applied=result.applied,
        disclaimer=result.disclaimer,
        note=note,
        note_source=note_source,
    )
