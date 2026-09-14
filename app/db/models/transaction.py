from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.portfolio import Portfolio
    from app.db.models.security import Security


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Transaction(Base):
    """A fill: buy or sell a quantity of one security in one portfolio.

    Index ``ix_transactions_portfolio_id_timestamp``
        Query: ``SELECT * FROM transactions WHERE portfolio_id = ?
        ORDER BY timestamp``. Ledger / history views.
        ``portfolio_id`` first (equality), ``timestamp`` second (order
        and range). Tradeoff: write amplification on each new fill.

    Index ``ix_transactions_portfolio_id_security_id``
        Query: ``SELECT * FROM transactions WHERE portfolio_id = ?
        AND security_id = ?``. Holdings for one ticker: sum BUY minus
        SELL. Column order matches the filter; a ``(security_id,
        portfolio_id)`` index would not help “all trades in this
        portfolio” lookups as well.
        Tradeoff: two indexes on the same table. We do **not** add
        ``transactions(security_id)`` — “every trade of AAPL across
        all users” is not a Phase 3 path.

    ``quantity`` and ``price`` are ``NUMERIC``. Share counts can be
    fractional; prices must not be floats.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_portfolio_id_timestamp", "portfolio_id", "timestamp"),
        Index(
            "ix_transactions_portfolio_id_security_id",
            "portfolio_id",
            "security_id",
        ),
        CheckConstraint(
            "transaction_type IN ('BUY', 'SELL')",
            name="type",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price > 0", name="price_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")
    security: Mapped[Security] = relationship(back_populates="transactions")
