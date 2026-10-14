from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_quote_store
from app.core.cache import CacheBackend, get_cache
from app.core.config import settings
from app.core.metrics import OperationalMetrics, get_metrics
from app.quotes.store import QuoteStore
from app.repositories.job_run_repository import (
    JOB_NAME_MARKET_DATA,
    JobRunRepository,
)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


class StatusResponse(BaseModel):
    status: str
    provider: dict[str, Any]
    ingestion: dict[str, Any] | None
    cache: dict[str, int | float]
    worker: dict[str, Any] | None
    metrics: dict[str, float]


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")


def redis_readiness() -> str:
    if not settings.cache_enabled:
        return "disabled"
    client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )
    try:
        return "ok" if client.ping() else "error"
    except RedisError:
        return "error"
    finally:
        client.close()


@router.get("/ready", response_model=ReadinessResponse)
def get_readiness(
    response: Response,
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    checks = {"postgresql": "error", "redis": redis_readiness()}
    try:
        db.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except (SQLAlchemyError, RuntimeError):
        pass
    ready = checks["postgresql"] == "ok" and checks["redis"] in {"ok", "disabled"}
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)


@router.get("/status", response_model=StatusResponse)
def get_status(
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
    quotes: QuoteStore = Depends(get_quote_store),
    metrics: OperationalMetrics = Depends(get_metrics),
) -> StatusResponse:
    quote_rows = quotes.snapshot()
    states: dict[str, int] = {}
    for quote in quote_rows:
        states[quote.timeliness] = states.get(quote.timeliness, 0) + 1
    latest = JobRunRepository(db).list_recent(
        job_name=JOB_NAME_MARKET_DATA,
        limit=1,
    )
    run = latest[0] if latest else None
    ingestion = None
    if run is not None:
        ingestion = {
            "job_name": run.job_name,
            "status": str(run.status),
            "provider": run.provider,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "fetched": run.fetched,
            "upserted": run.upserted,
            "failed_ticker_count": len(run.failed_tickers),
        }
    return StatusResponse(
        status="ok",
        provider={
            "name": settings.quote_provider,
            "quote_count": len(quote_rows),
            "freshness": states,
        },
        ingestion=ingestion,
        cache=cache.stats(),
        worker=quotes.get_worker_heartbeat(),
        metrics=metrics.snapshot(),
    )
