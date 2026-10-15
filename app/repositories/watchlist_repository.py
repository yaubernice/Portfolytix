from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Security, Watchlist, WatchlistItem


class WatchlistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_owned(self, watchlist_id: UUID, user_id: UUID) -> Watchlist | None:
        statement = select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == user_id,
        )
        return self.session.scalar(statement)

    def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Watchlist], int]:
        base = select(Watchlist).where(Watchlist.user_id == user_id)
        total = int(
            self.session.scalar(select(func.count()).select_from(base.subquery()))
            or 0
        )
        rows = list(
            self.session.scalars(
                base.order_by(Watchlist.created_at, Watchlist.id)
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def add(self, watchlist: Watchlist) -> Watchlist:
        self.session.add(watchlist)
        self.session.flush()
        self.session.refresh(watchlist)
        return watchlist

    def delete(self, watchlist: Watchlist) -> None:
        self.session.delete(watchlist)
        self.session.flush()

    def distinct_active_tickers(self, *, limit: int) -> list[str]:
        """Tickers on any watchlist. Inactive listings are left out."""
        statement = (
            select(Security.ticker)
            .join(WatchlistItem, WatchlistItem.security_id == Security.id)
            .where(Security.is_active.is_(True))
            .distinct()
            .order_by(Security.ticker)
            .limit(limit)
        )
        return [ticker for ticker in self.session.scalars(statement) if ticker]

    def count_items(self, watchlist_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(WatchlistItem)
            .where(WatchlistItem.watchlist_id == watchlist_id)
        )
        return int(self.session.scalar(statement) or 0)

    def list_items(
        self,
        watchlist_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[WatchlistItem], int]:
        base = select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        total = int(
            self.session.scalar(select(func.count()).select_from(base.subquery()))
            or 0
        )
        rows = list(
            self.session.scalars(
                base.options(joinedload(WatchlistItem.security))
                .order_by(WatchlistItem.created_at, WatchlistItem.id)
                .limit(limit)
                .offset(offset)
            ).unique()
        )
        return rows, total

    def find_item(
        self,
        watchlist_id: UUID,
        security_id: UUID,
    ) -> WatchlistItem | None:
        statement = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.security_id == security_id,
        )
        return self.session.scalar(statement)

    def add_item(self, item: WatchlistItem) -> WatchlistItem:
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def delete_item(self, item: WatchlistItem) -> None:
        self.session.delete(item)
        self.session.flush()
