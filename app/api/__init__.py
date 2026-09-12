from fastapi import FastAPI

from app.api.routes import health


def register_routes(app: FastAPI) -> None:
    """Attach HTTP routers. Handlers stay thin; domain logic belongs in services later."""
    app.include_router(health.router)
