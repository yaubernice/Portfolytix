from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Portfolio


class PortfolioRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, portfolio_id: UUID) -> Portfolio | None: #get portfolio by id
        return self.session.get(Portfolio, portfolio_id)

    def get_for_update(self, portfolio_id: UUID) -> Portfolio | None: 
        """Lock the portfolio row so two fills cannot oversell concurrently.

        ``SELECT ... FOR UPDATE`` serializes writers on this row until the
        transaction commits. SQLite ignores the clause; PostgreSQL honors it.
        """
        return self.session.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
        ).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[Portfolio]:
        statement = (
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .order_by(Portfolio.created_at, Portfolio.id) 
        )
        return list(self.session.scalars(statement))

    def add(self, portfolio: Portfolio) -> Portfolio:
        self.session.add(portfolio)
        self.session.flush()
        self.session.refresh(portfolio)
        return portfolio

    def delete(self, portfolio: Portfolio) -> None:
        self.session.delete(portfolio)
        self.session.flush()
