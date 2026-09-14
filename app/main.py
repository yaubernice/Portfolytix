import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api import register_exception_handlers, register_routes
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    logger.info(
        "startup",
        extra={"environment": settings.environment, "app": settings.app_name},
    )
    yield
    engine.dispose()
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Phase 3: portfolio and transaction API. "
        "Holdings are derived from the ledger. Auth is not implemented yet."
    ),
    lifespan=lifespan,
)

register_routes(app)
register_exception_handlers(app)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
        },
    )
    return response
