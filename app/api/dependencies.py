from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.cache import CacheBackend, commit_and_invalidate, get_cache
from app.db.session import SessionLocal
from app.services.analytics_service import AnalyticsService
from app.services.job_service import JobService
from app.services.portfolio_service import PortfolioService
from app.services.screening_service import ScreeningService


def get_db(
    cache: CacheBackend = Depends(get_cache),
) -> Generator[Session, None, None]: #commit and rollback transactions
    """Yield a request-scoped session. Commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        commit_and_invalidate(db, cache)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_portfolio_service(
    db: Session = Depends(get_db),
) -> PortfolioService:
    return PortfolioService(db)


def get_analytics_service(
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
) -> AnalyticsService:
    return AnalyticsService(db, cache)


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db)


def get_screening_service(
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
) -> ScreeningService:
    return ScreeningService(db, cache)
