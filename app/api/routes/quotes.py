from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_current_user, get_quote_store
from app.core.config import settings
from app.core.exceptions import AppError, AuthenticationError
from app.core.metrics import get_metrics
from app.core.security import decode_access_token
from app.db.models import User
from app.quotes.store import QuoteStore
from app.quotes.symbols import normalize_quote_symbols
from app.schemas.market import QuotesResponse

router = APIRouter(tags=["quotes"])


@router.get("/quotes", response_model=QuotesResponse)
def list_quotes(
    tickers: str = "",
    _user: User = Depends(get_current_user),
    store: QuoteStore = Depends(get_quote_store),
) -> QuotesResponse:
    try:
        parsed = normalize_quote_symbols(tickers, limit=settings.quote_max_symbols)
    except ValueError as exc:
        raise AppError(str(exc), status_code=422) from exc
    symbols = parsed or None
    quotes = store.snapshot(symbols)
    metrics = get_metrics()
    metrics.gauge("market.quote_count", len(quotes))
    metrics.gauge(
        "market.stale_quotes",
        sum(quote.is_stale for quote in quotes),
    )
    return QuotesResponse(quotes=quotes)


@router.websocket("/ws/quotes")
async def quote_stream(
    websocket: WebSocket,
    token: str = Query(default=""),
    store: QuoteStore = Depends(get_quote_store),
) -> None:
    """Relay Redis pub/sub to the browser. The API does not fetch the vendor."""
    await websocket.accept()
    try:
        decode_access_token(token)
    except AuthenticationError:
        await websocket.send_json(
            {"type": "error", "detail": "Invalid or expired access token"}
        )
        await websocket.close(code=1008)
        return
    metrics = get_metrics()
    metrics.increment("websocket.clients")
    subscription = store.subscription()
    try:
        snapshot = store.snapshot()
        await websocket.send_json(
            {
                "type": "snapshot",
                "quotes": [quote.model_dump(mode="json") for quote in snapshot],
            }
        )
        async for quote in subscription:
            await websocket.send_json(
                {"type": "quote", "quote": quote.model_dump(mode="json")}
            )
    except WebSocketDisconnect:
        return
    finally:
        await subscription.aclose()
        metrics.increment("websocket.clients", -1)
