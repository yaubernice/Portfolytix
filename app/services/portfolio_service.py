from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.cache import queue_version_bump
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.db.models import Portfolio, Transaction
from app.db.models.transaction import TransactionType
from app.quotes.provider_marks import provider_quotes
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.security_repository import SecurityRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.holding import HoldingOut
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioDetail,
    PortfolioSummary,
    PortfolioUpdate,
)
from app.schemas.transaction import TransactionCreate, TransactionOut
from app.services.holdings import PositionLeg, aggregate_positions, quantity_held


class PortfolioService:
    def __init__(self, session: Session, user_id: UUID) -> None:
        self.user_id = user_id
        self.portfolios = PortfolioRepository(session)
        self.securities = SecurityRepository(session)
        self.transactions = TransactionRepository(session)

    def create_portfolio(self, payload: PortfolioCreate) -> PortfolioSummary: 
        portfolio = Portfolio(
            user_id=self.user_id,
            name=payload.name,
            description=payload.description,
        )
        return PortfolioSummary.model_validate(self.portfolios.add(portfolio))

#The authenticated user can only list their own portfolios.
    def list_portfolios(self) -> list[PortfolioSummary]:
        return [
            PortfolioSummary.model_validate(row)
            for row in self.portfolios.list_for_user(self.user_id)
        ]

    def get_portfolio(self, portfolio_id: UUID) -> PortfolioDetail:
        portfolio = self._require_portfolio(portfolio_id)
        return self._detail(portfolio)

    def update_portfolio(
        self, portfolio_id: UUID, payload: PortfolioUpdate
    ) -> PortfolioDetail:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise AppError("PATCH requires at least one field", status_code=422)
        portfolio = self._require_portfolio(portfolio_id)
        if "name" in data:
            portfolio.name = data["name"]
        if "description" in data:
            portfolio.description = data["description"]
        self.portfolios.session.flush()
        self.portfolios.session.refresh(portfolio)
        return self._detail(portfolio)

    def delete_portfolio(self, portfolio_id: UUID) -> None:
        portfolio = self._require_portfolio(portfolio_id)
        self.portfolios.delete(portfolio)
        queue_version_bump(
            self.portfolios.session,
            f"portfolio:{portfolio_id}",
        )

    def list_holdings(self, portfolio_id: UUID) -> list[HoldingOut]:
        self._require_portfolio(portfolio_id)
        return self._holdings(portfolio_id)

    def list_transactions(self, portfolio_id: UUID) -> list[TransactionOut]:
        self._require_portfolio(portfolio_id)
        rows = self.transactions.list_for_portfolio(portfolio_id)
        return [self._transaction_out(row) for row in rows]

    def add_transaction(  #check ownership and lock the portfolio row for update
        self, portfolio_id: UUID, payload: TransactionCreate
    ) -> TransactionOut:
        portfolio = self.portfolios.get_owned_for_update(
            portfolio_id,
            self.user_id,
        )
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")

        ticker = payload.ticker.upper()
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker} not found")

        if payload.quantity != payload.quantity.to_integral_value():
            raise ConflictError("Buy and sell a whole number of shares.")
        if payload.quantity < 1:
            raise ConflictError("The smallest order is 1 share.")

        holdings = self._holdings(portfolio_id)
        held = quantity_held(holdings, security.id)
        if payload.transaction_type is TransactionType.SELL and payload.quantity > held:
            raise ConflictError(
                f"Cannot SELL {payload.quantity} {ticker}; "
                f"current position is {held}"
            )

        price = payload.price
        if settings.provider_marks:
            quote = provider_quotes([ticker]).get(ticker)
            if quote is None:
                raise ConflictError(
                    f"No latest provider price is available for {ticker}."
                )
            price = quote.price

        row = Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type=payload.transaction_type.value,
            quantity=payload.quantity,
            price=price,
            timestamp=payload.timestamp or datetime.now(UTC),
        )
        saved = self.transactions.add(row)
        saved.security = security #add security object to the transaction object
        queue_version_bump(
            self.portfolios.session,
            f"portfolio:{portfolio_id}",
        )
        return self._transaction_out(saved)

    def _require_portfolio(self, portfolio_id: UUID) -> Portfolio:
        portfolio = self.portfolios.get_owned(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return portfolio

    def _holdings(self, portfolio_id: UUID) -> list[HoldingOut]: 
        legs = [
            PositionLeg(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
            )
            for row in self.transactions.list_for_portfolio(portfolio_id)
        ]
        return aggregate_positions(legs)

    def _detail(self, portfolio: Portfolio) -> PortfolioDetail: 
        summary = PortfolioSummary.model_validate(portfolio)
        return PortfolioDetail(
            **summary.model_dump(),
            holdings=self._holdings(portfolio.id),
        )

    def _transaction_out(self, row: Transaction) -> TransactionOut:
        return TransactionOut(
            id=row.id,
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            ticker=row.security.ticker,
            transaction_type=TransactionType(row.transaction_type),
            quantity=row.quantity,
            price=row.price,
            timestamp=row.timestamp,
            created_at=row.created_at,
        )
