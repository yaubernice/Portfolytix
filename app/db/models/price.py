from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.security import Security

# Six decimal places covers US equity prints without using binary floats.
_PRICE = Numeric(18, 6)


class Price(Base):
    """One daily OHLCV bar for one security.

    Unique ``(security_id, timestamp)`` — also the history index
        Query: ``SELECT * FROM prices WHERE security_id = ? AND timestamp
        BETWEEN ? AND ? ORDER BY timestamp``.
        Column order: equality on ``security_id`` first, range on
        ``timestamp`` second. Postgres can walk the btree from the
        security's first bar to its last. Reversing the columns would
        force a scan of every security at a given time (useless here).
        The same index enforces uniqueness so a repeated ingest cannot
        insert a second bar for the same day.
        Tradeoff: every insert updates this unique index. That is the
        correct cost for a table that will later hold millions of rows.

    No separate ``security_id``-only index: the unique composite already
    leads with ``security_id``, so FK lookups can use it.

    Monetary columns are ``NUMERIC``, never ``FLOAT`` / ``REAL``. Binary
    floating point cannot represent 0.1 exactly and would drift in
    return calculations.
    """

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "timestamp",
            name="uq_prices_security_id_timestamp",
        ),
        CheckConstraint("high >= low", name="high_gte_low"),
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0"
            " AND close > 0 AND adjusted_close > 0",
            name="positive",
        ),
        CheckConstraint("volume >= 0", name="volume_nonnegative"),
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
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    high: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    low: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    close: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    adjusted_close: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    security: Mapped[Security] = relationship(back_populates="prices")
