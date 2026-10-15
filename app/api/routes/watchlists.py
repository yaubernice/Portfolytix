from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_watchlist_service
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistDetail,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistPage,
    WatchlistSummary,
    WatchlistUpdate,
)
from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.post("", response_model=WatchlistSummary, status_code=status.HTTP_201_CREATED)
def create_watchlist(
    payload: WatchlistCreate,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistSummary:
    return service.create(payload)


@router.get("", response_model=WatchlistPage)
def list_watchlists(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistPage:
    return service.list_watchlists(limit=limit, offset=offset)


@router.get("/{watchlist_id}", response_model=WatchlistDetail)
def get_watchlist(
    watchlist_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistDetail:
    return service.get(watchlist_id, limit=limit, offset=offset)


@router.patch("/{watchlist_id}", response_model=WatchlistSummary)
def rename_watchlist(
    watchlist_id: UUID,
    payload: WatchlistUpdate,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistSummary:
    return service.rename(watchlist_id, payload)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    watchlist_id: UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> Response:
    service.delete(watchlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{watchlist_id}/items",
    response_model=WatchlistItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_watchlist_item(
    watchlist_id: UUID,
    payload: WatchlistItemCreate,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistItemOut:
    return service.add_item(watchlist_id, payload)


@router.delete(
    "/{watchlist_id}/items/{security_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_watchlist_item(
    watchlist_id: UUID,
    security_id: UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> Response:
    service.remove_item(watchlist_id, security_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
