from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import (
    analytics,
    assistant,
    auth,
    cache,
    health,
    holdings,
    jobs,
    learning,
    portfolios,
    positions,
    quotes,
    reference,
    research,
    screening,
    transactions,
    watchlists,
)
from app.core.exceptions import AppError


def register_routes(app: FastAPI) -> None:
    """Attach HTTP routers. Handlers stay thin; services own domain logic."""
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(portfolios.router)
    app.include_router(watchlists.router)
    app.include_router(transactions.router)
    app.include_router(holdings.router)
    app.include_router(positions.router)
    app.include_router(analytics.router)
    app.include_router(quotes.router)
    app.include_router(reference.router)
    app.include_router(assistant.router)
    app.include_router(assistant.tools_router)
    app.include_router(jobs.router)
    app.include_router(screening.router)
    app.include_router(research.router)
    app.include_router(learning.router)
    app.include_router(cache.router)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers=exc.headers,
        )
