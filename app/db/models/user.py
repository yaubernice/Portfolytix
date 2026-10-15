from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.flag import ResearchFlag
    from app.db.models.portfolio import Portfolio
    from app.db.models.watchlist import Watchlist


class User(Base):
    """Account row. Auth (hashing, JWT) is Phase 10; the table exists now
    so portfolios can already reference a real ``users.id``.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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

    portfolios: Mapped[list[Portfolio]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    watchlists: Mapped[list[Watchlist]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    research_flags: Mapped[list[ResearchFlag]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
