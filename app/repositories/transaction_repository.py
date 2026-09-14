from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Transaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_portfolio(self, portfolio_id: UUID) -> list[Transaction]:
        statement = (
            select(Transaction)
            .options(joinedload(Transaction.security))
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.timestamp, Transaction.created_at, Transaction.id)
        )
        return list(self.session.scalars(statement).unique())

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        self.session.flush()
        self.session.refresh(transaction)
        return transaction
