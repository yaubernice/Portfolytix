from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.security import Security
    from app.db.models.user import User


class ResearchFlag(Base):
    """A user mark on one security or one sector. Not a price alert."""

    __tablename__ = "research_flags"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('security', 'sector')",
            name="target_type",
        ),
        CheckConstraint(
            "(target_type = 'security' AND security_id IS NOT NULL "
            "AND sector IS NULL) OR "
            "(target_type = 'sector' AND sector IS NOT NULL "
            "AND security_id IS NULL)",
            name="target",
        ),
        Index("ix_research_flags_user_id", "user_id"),
        Index(
            "uq_research_flags_user_security",
            "user_id",
            "security_id",
            unique=True,
            sqlite_where=text("security_id IS NOT NULL"),
            postgresql_where=text("security_id IS NOT NULL"),
        ),
        Index(
            "uq_research_flags_user_sector",
            "user_id",
            "sector",
            unique=True,
            sqlite_where=text("sector IS NOT NULL"),
            postgresql_where=text("sector IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    security_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=True,
    )
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="research_flags")
    security: Mapped[Security | None] = relationship()
