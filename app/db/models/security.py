from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.price import Price
    from app.db.models.transaction import Transaction


class Security(Base):
    """Tradable instrument (dimension table). Prices live in ``prices``.

    Unique index on ``ticker``
        Query: ``SELECT * FROM securities WHERE ticker = 'AAPL'``.
        Tickers are the public lookup key; the unique index is both a
        constraint (no duplicate listings) and the access path.
        Tradeoff: ticker renames or dual-listed symbols would need a
        later mapping table. One row per ticker is enough for Phase 2.
    """

    __tablename__ = "securities"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    prices: Mapped[list[Price]] = relationship(
        back_populates="security",
        cascade="all, delete-orphan",
    )
    # passive_deletes: the FK is ON DELETE RESTRICT. SQLAlchemy must not
    # SET transactions.security_id = NULL when a Security is deleted.
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="security",
        passive_deletes=True,
    )
