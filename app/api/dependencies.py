from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
