from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import Security, User
from app.schemas.portfolio import PortfolioCreate
from app.schemas.transaction import TransactionCreate
from app.services.portfolio_service import PortfolioService


def test_postgres_buy_buy_sell_derives_holdings(postgres_session: Session) -> None:
    user = User(
        email=f"ledger-{uuid4()}@example.com",
        password_hash="not-used",
    )
    security = Security(
        ticker="P11A",
        name="Phase 11 Test",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    postgres_session.add_all([user, security])
    postgres_session.flush()

    service = PortfolioService(postgres_session, user.id)
    portfolio = service.create_portfolio(PortfolioCreate(name="Core"))
    for quantity in ("10", "5"):
        service.add_transaction(
            portfolio.id,
            TransactionCreate(
                ticker="p11a",
                transaction_type="BUY",
                quantity=Decimal(quantity),
                price=Decimal("100"),
            ),
        )
    service.add_transaction(
        portfolio.id,
        TransactionCreate(
            ticker="P11A",
            transaction_type="SELL",
            quantity=Decimal("3"),
            price=Decimal("110"),
        ),
    )

    holdings = service.list_holdings(portfolio.id)
    assert len(holdings) == 1
    assert holdings[0].ticker == "P11A"
    assert holdings[0].quantity == Decimal("12")
    assert service.list_transactions(portfolio.id)[0].quantity == Decimal("10")
