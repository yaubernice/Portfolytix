from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Watchlist, WatchlistItem
from app.repositories.security_repository import SecurityRepository
from app.repositories.watchlist_repository import WatchlistRepository
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistDetail,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistPage,
    WatchlistSummary,
    WatchlistUpdate,
)


class WatchlistService:
    def __init__(self, session: Session, user_id: UUID) -> None:
        self.user_id = user_id
        self.session = session
        self.watchlists = WatchlistRepository(session)
        self.securities = SecurityRepository(session)

    def create(self, payload: WatchlistCreate) -> WatchlistSummary:
        saved = self.watchlists.add(
            Watchlist(user_id=self.user_id, name=payload.name)
        )
        return self._summary(saved, item_count=0)

    def list_watchlists(self, *, limit: int, offset: int) -> WatchlistPage:
        rows, total = self.watchlists.list_for_user(
            self.user_id,
            limit=limit,
            offset=offset,
        )
        return WatchlistPage(
            items=[
                self._summary(row, self.watchlists.count_items(row.id)) for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(
        self,
        watchlist_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> WatchlistDetail:
        watchlist = self._require(watchlist_id)
        items, total = self.watchlists.list_items(
            watchlist.id,
            limit=limit,
            offset=offset,
        )
        summary = self._summary(watchlist, total)
        return WatchlistDetail(
            **summary.model_dump(),
            items=[self._item(row) for row in items],
            items_total=total,
            items_limit=limit,
            items_offset=offset,
        )

    def rename(self, watchlist_id: UUID, payload: WatchlistUpdate) -> WatchlistSummary:
        watchlist = self._require(watchlist_id)
        watchlist.name = payload.name
        self.session.flush()
        self.session.refresh(watchlist)
        return self._summary(watchlist, self.watchlists.count_items(watchlist.id))

    def delete(self, watchlist_id: UUID) -> None:
        watchlist = self._require(watchlist_id)
        self.watchlists.delete(watchlist)

    def add_item(
        self,
        watchlist_id: UUID,
        payload: WatchlistItemCreate,
    ) -> WatchlistItemOut:
        watchlist = self._require(watchlist_id)
        security = self.securities.get_by_id(payload.security_id) #get security by ID
        if security is None:
            raise NotFoundError(f"Security {payload.security_id} not found")
        #check for duplicate
        existing = self.watchlists.find_item(watchlist.id, security.id)
        if existing is not None:
            raise ConflictError(
                f"{security.ticker} is already on watchlist {watchlist.id}"
            )
        saved = self.watchlists.add_item(
            WatchlistItem(watchlist_id=watchlist.id, security_id=security.id)
        )
        saved.security = security
        return self._item(saved)

    def remove_item(self, watchlist_id: UUID, security_id: UUID) -> None:
        watchlist = self._require(watchlist_id)
        item = self.watchlists.find_item(watchlist.id, security_id)
        if item is None:
            raise NotFoundError(
                f"Security {security_id} is not on watchlist {watchlist_id}"
            )
        self.watchlists.delete_item(item)

    def _require(self, watchlist_id: UUID) -> Watchlist:
        watchlist = self.watchlists.get_owned(watchlist_id, self.user_id)
        if watchlist is None:
            raise NotFoundError(f"Watchlist {watchlist_id} not found")
        return watchlist

    def _summary(self, watchlist: Watchlist, item_count: int) -> WatchlistSummary:
        return WatchlistSummary(
            id=watchlist.id,
            name=watchlist.name,
            item_count=item_count,
            created_at=watchlist.created_at,
            updated_at=watchlist.updated_at,
        )

    def _item(self, item: WatchlistItem) -> WatchlistItemOut:
        security = item.security
        return WatchlistItemOut(
            id=item.id,
            security_id=item.security_id,
            ticker=security.ticker,
            name=security.name,
            exchange=security.exchange,
            created_at=item.created_at,
        )
