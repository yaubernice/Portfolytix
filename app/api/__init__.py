from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import (
    analytics,
    cache,
    health,
    holdings,
    jobs,
    portfolios,
    screening,
    transactions,
)
from app.core.exceptions import AppError


def register_routes(app: FastAPI) -> None:
    """Attach HTTP routers. Handlers stay thin; services own domain logic."""
    app.include_router(health.router)
    app.include_router(portfolios.router)
    app.include_router(transactions.router)
    app.include_router(holdings.router)
    app.include_router(analytics.router)
    app.include_router(jobs.router)
    app.include_router(screening.router)
    app.include_router(cache.router)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )
