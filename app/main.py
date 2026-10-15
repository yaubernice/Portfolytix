#Configure startup/shutdown
#Create FastAPI app
#Register routes
#Register exception handlers
#Log requests

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import register_exception_handlers, register_routes
from app.core.cache import commit_and_invalidate, get_cache
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
        "Authenticated portfolio API with analytics, daily bars in PostgreSQL, "
        "live quotes in Redis, structured screening, and an assistant that "
        "answers from stored evidence. Not investment advice."
    ),
    lifespan=lifespan,
)

register_routes(app) #Attach API routes to the app
register_exception_handlers(app) #Attach exception handlers to the app

_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

_ui_dir = Path(__file__).resolve().parents[1] / "frontend"
if _ui_dir.is_dir():
    app.mount("/ui", StaticFiles(directory=_ui_dir, html=True), name="ui")


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    # Commit before the body is sent. Code after a dependency yield runs too late
    # for a client that immediately reads the row it just created.
    db = getattr(request.state, "db", None)
    cache = getattr(request.state, "cache", None)
    if db is not None and cache is not None and response.status_code < 400:
        commit_and_invalidate(db, cache)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
        },
    )
    return response
