from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Security, Transaction
from app.db.models.transaction import TransactionType


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_portfolio(self, portfolio_id: UUID) -> list[Transaction]:
        statement = (
            select(Transaction)
            # analytics needs row.security.ticker, so join the security table
            .options(joinedload(Transaction.security))
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.timestamp, Transaction.created_at, Transaction.id)
        )
        # unique() collapses joinedload duplicates; returns Transaction objects
        return list(self.session.scalars(statement).unique())

    def distinct_open_tickers(self, *, limit: int) -> list[str]:
        """Tickers with a positive share balance. A flat position is left out."""
        signed = case(
            (Transaction.transaction_type == TransactionType.BUY, Transaction.quantity),
            else_=-Transaction.quantity,
        )
        statement = (
            select(Security.ticker)
            .join(Transaction, Transaction.security_id == Security.id)
            .where(Security.is_active.is_(True))
            .group_by(Security.ticker)
            .having(func.sum(signed) > 0)
            .order_by(Security.ticker)
            .limit(limit)
        )
        return [ticker for ticker in self.session.scalars(statement) if ticker]

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        self.session.flush()
        self.session.refresh(transaction)
        return transaction
