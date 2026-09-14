from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.portfolio_service import PortfolioService


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session. Commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_portfolio_service(db: Session = Depends(get_db)) -> PortfolioService:
    return PortfolioService(db)
