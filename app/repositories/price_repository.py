from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Price


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_closes(
        self, security_ids: list[UUID]
    ) -> list[tuple[UUID, datetime, Decimal]]:
        if not security_ids:
            return []
        statement = (
            select(Price.security_id, Price.timestamp, Price.adjusted_close)
            .where(Price.security_id.in_(security_ids))
            .order_by(Price.security_id, Price.timestamp) #sort by timestamp
        )
        return list(self.session.execute(statement).all()) #returns a list of tuples (security_id, timestamp, adjusted_close)
