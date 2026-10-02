from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.security import Security

# Ratios (ROE, growth) and multiples (P/E) stay Decimal, never float.
_RATIO = Numeric(18, 8)
_MONEY = Numeric(20, 2)


class Fundamental(Base):
    """Latest fundamental snapshot for one security.

    One row per security (unique ``security_id``). This is a current
    screen, not a fundamentals time series. History can be added later
    with ``(security_id, as_of)`` if Phase 8 measures a need for it.

    Unique ``security_id``
        Query: ``SELECT * FROM fundamentals WHERE security_id = ?``.
        Also the join key from ``securities``.
        Tradeoff: a new snapshot overwrites the old one. Screening
        “current ROE” does not need quarters of history.

    No indexes on ``roe`` / ``pe_ratio`` / … yet. Seven seeded rows do
    not need them. Phase 8 will measure before adding filter indexes.
    """

    __tablename__ = "fundamentals"
    __table_args__ = (
        UniqueConstraint("security_id", name="uq_fundamentals_security_id"),
        CheckConstraint("market_cap > 0", name="market_cap_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    security_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    # 0.15 = 15% net income / equity. Can be negative.
    roe: Mapped[Decimal] = mapped_column(_RATIO, nullable=False)
    # Price / earnings multiple. Can be negative when earnings are.
    pe_ratio: Mapped[Decimal] = mapped_column(_RATIO, nullable=False)
    # 0.10 = 10% year-over-year revenue change. Can be negative.
    revenue_growth: Mapped[Decimal] = mapped_column(_RATIO, nullable=False)
    # USD, not billions. 10000000000 = $10B.
    market_cap: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
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

    security: Mapped[Security] = relationship(back_populates="fundamental")
