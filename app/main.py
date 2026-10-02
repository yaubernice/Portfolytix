#Configure startup/shutdown
#Create FastAPI app
#Register routes
#Register exception handlers
#Log requests

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api import register_exception_handlers, register_routes
from app.core.cache import get_cache
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.jobs.scheduler import start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    logger.info(
        "startup",
        extra={"environment": settings.environment, "app": settings.app_name},
    )
    cache = get_cache()
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    cache.close()
    engine.dispose() #close all connections to the database
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Phase 9: portfolio API, analytics, market-data ingest, "
        "structured screening, query optimization, and Redis caching. "
        "Not investment advice. Auth is not implemented yet."
    ),
    lifespan=lifespan,
)

register_routes(app) #Attach API routes to the app
register_exception_handlers(app) #Attach exception handlers to the app


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
