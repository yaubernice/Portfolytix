from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.fundamental import Fundamental
    from app.db.models.price import Price
    from app.db.models.transaction import Transaction


ASSET_TYPES = ("equity", "etf", "fund", "index", "other")


class Security(Base):
    """Tradable instrument (dimension table). Prices live in ``prices``.

    Identity is ``(provider, provider_symbol)``, not ticker.
        The same letters can list on two venues or two vendors.
        Query: ``WHERE provider = ? AND provider_symbol = ?``.
        Ticker stays indexed for search and for the common one-listing case.
        A ticker lookup that matches several active rows is ambiguous.
    """

    __tablename__ = "securities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_symbol",
            name="uq_securities_provider_symbol",
        ),
        Index("ix_securities_ticker", "ticker"),
        CheckConstraint(
            "asset_type IN ('equity', 'etf', 'fund', 'index', 'other')",
            name="ck_securities_asset_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    mic: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sector: Mapped[str] = mapped_column(String(64), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    asset_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="equity",
        server_default="equity",
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    provider_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
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
    fundamental: Mapped[Fundamental | None] = relationship(
        back_populates="security",
        cascade="all, delete-orphan",
        uselist=False,
    )


@event.listens_for(Security, "before_insert")
@event.listens_for(Security, "before_update")
def _fill_provider_identity(_mapper, _connection, target: Security) -> None:
    """Core inserts set these explicitly. ORM inserts may omit them."""
    if target.ticker:
        target.ticker = target.ticker.strip().upper()
    if not target.provider:
        target.provider = "manual"
    else:
        target.provider = target.provider.strip().lower()
    if not target.provider_symbol:
        target.provider_symbol = target.ticker
    else:
        target.provider_symbol = target.provider_symbol.strip().upper()
