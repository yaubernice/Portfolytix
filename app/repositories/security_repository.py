from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Security


class SecurityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_ticker(self, ticker: str) -> Security | None:
        statement = select(Security).where(Security.ticker == ticker.upper())
        return self.session.scalar(statement)
