from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.models import Security


class SecurityQuery:
    """Bound search values. Callers do not pass SQL fragments."""

    def __init__(
        self,
        *,
        q: str | None = None,
        exchange: str | None = None,
        country: str | None = None,
        sector: str | None = None,
        asset_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> None:
        self.q = q
        self.exchange = exchange
        self.country = country
        self.sector = sector
        self.asset_type = asset_type
        self.limit = limit
        self.offset = offset


class SecurityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, security_id: UUID) -> Security | None:
        return self.session.get(Security, security_id)

    def get_by_ticker(self, ticker: str) -> Security | None:
        """Return the one active listing for a ticker.

        Several active rows with the same ticker are a conflict. Callers
        that already know the security id should use ``get_by_id``.
        """
        symbol = ticker.strip().upper()
        statement = (
            select(Security)
            .where(Security.ticker == symbol)
            .order_by(Security.is_active.desc(), Security.created_at)
        )
        rows = list(self.session.scalars(statement))
        active = [row for row in rows if row.is_active]
        chosen = active or rows
        if len(chosen) > 1:
            raise ConflictError(
                f"Ticker {symbol} matches more than one security; use its id"
            )
        if not chosen:
            return None
        return chosen[0]

    def list_for_ingest(
        self,
        *,
        exchange: str | None,
        country: str | None,
        limit: int,
    ) -> tuple[list[Security], int]:
        """Active listings for one exchange or country, capped by ``limit``."""
        statement = select(Security).where(Security.is_active.is_(True))
        if exchange:
            statement = statement.where(
                func.lower(Security.exchange) == exchange.strip().lower()
            )
        if country:
            statement = statement.where(
                func.lower(Security.country) == country.strip().lower()
            )
        total = int(
            self.session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                statement.order_by(Security.ticker, Security.id).limit(limit)
            )
        )
        return rows, total

    def search(self, query: SecurityQuery) -> tuple[list[Security], int]:
        statement = select(Security).where(Security.is_active.is_(True))
        if query.q and query.q.strip():
            pattern = _contains(query.q)
            statement = statement.where(
                or_(
                    Security.ticker.ilike(pattern, escape="\\"),
                    Security.name.ilike(pattern, escape="\\"),
                )
            )
        if query.exchange:
            statement = statement.where(
                func.lower(Security.exchange) == query.exchange.strip().lower()
            )
        if query.country:
            statement = statement.where(
                func.lower(Security.country) == query.country.strip().lower()
            )
        if query.sector:
            statement = statement.where(
                func.lower(Security.sector) == query.sector.strip().lower()
            )
        if query.asset_type:
            statement = statement.where(Security.asset_type == query.asset_type)
        total = int(
            self.session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            or 0
        )
        order = [Security.ticker, Security.exchange, Security.id]
        if query.q and query.q.strip():
            symbol = query.q.strip().upper()
            prefix = _contains(symbol).strip("%")
            order = [
                case(
                    (func.upper(Security.ticker) == symbol, 0),
                    (Security.ticker.ilike(f"{prefix}%", escape="\\"), 1),
                    else_=2,
                ),
                *order,
            ]
        rows = list(
            self.session.scalars(
                statement.order_by(*order).limit(query.limit).offset(query.offset)
            )
        )
        return rows, total


def _contains(value: str) -> str:
    escaped = (
        value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"
