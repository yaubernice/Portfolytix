from fastapi import APIRouter, Depends

from app.api.dependencies import get_screening_service
from app.schemas.screening import ScreenRequest, ScreenResponse
from app.services.screening_service import ScreeningService

router = APIRouter(prefix="/screen", tags=["screening"])


@router.post("", response_model=ScreenResponse)
def screen(
    payload: ScreenRequest,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreenResponse:
    return service.screen(payload)
