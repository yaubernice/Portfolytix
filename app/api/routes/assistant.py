from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse

from app.ai.tools import SafeToolExecutor, validate_tool_call
from app.api.dependencies import get_assistant_service, get_safe_tool_executor
from app.schemas.assistant import AskRequest, AssistantAnswer
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["assistant"])
tools_router = APIRouter(prefix="/assistant", tags=["assistant"])


@tools_router.post("/tools/execute")
def execute_safe_tool(
    payload: dict[str, Any] = Body(),
    executor: SafeToolExecutor = Depends(get_safe_tool_executor),
) -> dict:
    """Execute one authenticated allowlisted operation."""
    return executor.execute(validate_tool_call(payload))


@router.post("/ask", response_model=AssistantAnswer)
def ask_portfolio(
    portfolio_id: UUID,
    payload: AskRequest,
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantAnswer:
    return service.ask(portfolio_id, payload.question)


@router.post("/ask/stream")
def stream_portfolio_answer(
    portfolio_id: UUID,
    payload: AskRequest,
    service: AssistantService = Depends(get_assistant_service),
) -> StreamingResponse:
    # Resolve ownership and evidence before the streaming response starts.
    prepared = service.prepare(portfolio_id)
    return StreamingResponse(
        service.stream(prepared, payload.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
