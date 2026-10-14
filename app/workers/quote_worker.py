"""Publish latest quotes to Redis. This process is not the FastAPI server.

Daily bars still arrive through the scheduled ingest into PostgreSQL.
A trade tick updates `finsight:live:{ticker}` and the pub/sub channel only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.metrics import get_metrics
from app.db.models import Fundamental
from app.db.session import SessionLocal
from app.market_data.errors import ProviderError
from app.market_data.finnhub import (
    FINNHUB_WS,
    finnhub_subscribe_frame,
    finnhub_unsubscribe_frame,
    parse_finnhub_trades,
)
from app.quotes.factory import build_news_source, build_quote_source
from app.quotes.store import QuoteStoreError, RedisQuoteStore
from app.quotes.symbols import load_quote_symbols, subscription_delta
from app.repositories.security_repository import SecurityRepository

logger = logging.getLogger(__name__)


def publish_heartbeat(
    store: RedisQuoteStore,
    *,
    provider: str,
    symbols: list[str] | set[str],
    last_publish_at: datetime | None = None,
    last_poll_at: datetime | None = None,
    state: str = "running",
) -> None:
    """Publish non-sensitive worker liveness and workload metadata."""
    try:
        store.put_worker_heartbeat(
            {
                "provider": provider,
                "symbol_count": len(symbols),
                "active_subscriptions": sorted(symbols),
                "last_publish_at": (
                    last_publish_at.isoformat() if last_publish_at else None
                ),
                "last_poll_at": last_poll_at.isoformat() if last_poll_at else None,
                "heartbeat_at": datetime.now(UTC).isoformat(),
                "state": state,
            }
        )
    except QuoteStoreError:
        logger.warning("quote_worker_heartbeat_failed")


def build_worker_store() -> RedisQuoteStore:
    return RedisQuoteStore(
        settings.redis_url,
        prefix=settings.cache_key_prefix,
        ttl_seconds=settings.quote_ttl_seconds,
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
    )


def refresh_news(source: object, store: RedisQuoteStore, symbols: list[str]) -> None:
    capabilities = getattr(source, "capabilities", None)
    if capabilities is None or not capabilities.supports_news:
        return
    if not hasattr(source, "fetch_news"):
        return
    today = datetime.now(UTC).date()
    start = (today - timedelta(days=7)).isoformat()
    end = today.isoformat()
    for symbol in symbols:
        try:
            if source.name == "finnhub":
                items = source.fetch_news(symbol, start, end)
            else:
                items = source.fetch_news(symbol)
        except (ProviderError, TypeError) as exc:
            logger.warning(
                "news_refresh_failed",
                extra={"ticker": symbol, "error": str(exc)},
            )
            continue
        try:
            store.put_news(symbol, items[:8])
        except QuoteStoreError:
            logger.warning("news_store_failed", extra={"ticker": symbol})


def refresh_overviews(source: object, symbols: list[str]) -> None:
    if not hasattr(source, "fetch_overview"):
        return
    session = SessionLocal()
    try:
        securities = SecurityRepository(session)
        for symbol in symbols:
            try:
                fields = source.fetch_overview(symbol)
            except ProviderError as exc:
                logger.warning(
                    "overview_refresh_failed",
                    extra={"ticker": symbol, "error": str(exc)},
                )
                continue
            security = securities.get_by_ticker(symbol)
            if security is None:
                continue
            row = session.scalar(
                select(Fundamental).where(Fundamental.security_id == security.id)
            )
            if row is None:
                continue
            columns = {column.key for column in row.__table__.columns}
            for key, value in fields.items():
                if value is not None and key in columns:
                    setattr(row, key, value)
            row.provider = getattr(source, "name", None) or "alpha_vantage"
            row.as_of = date.today()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("overview_refresh_failed")
    finally:
        session.close()


async def _stream_session(
    api_key: str,
    symbols: list[str],
    store: RedisQuoteStore,
) -> None:
    import websockets

    # The key belongs in the Finnhub URL. Do not log this address.
    url = f"{FINNHUB_WS}?token={api_key}"
    async with websockets.connect(url) as socket:
        subscribed = set(symbols)
        metrics = get_metrics()
        last_publish_at: datetime | None = None
        for symbol in symbols:
            await socket.send(finnhub_subscribe_frame(symbol))
        metrics.gauge("quotes.active_subscriptions", len(subscribed))
        publish_heartbeat(store, provider="finnhub", symbols=subscribed)
        logger.info("quote_stream_started", extra={"symbols": len(symbols)})
        refreshed = time.monotonic()
        while True:
            if time.monotonic() - refreshed >= settings.quote_symbol_refresh_seconds:
                wanted = load_quote_symbols()
                added, removed = subscription_delta(subscribed, wanted)
                for symbol in removed:
                    await socket.send(finnhub_unsubscribe_frame(symbol))
                    subscribed.discard(symbol)
                for symbol in added:
                    await socket.send(finnhub_subscribe_frame(symbol))
                    subscribed.add(symbol)
                metrics.gauge("quotes.active_subscriptions", len(subscribed))
                publish_heartbeat(
                    store,
                    provider="finnhub",
                    symbols=subscribed,
                    last_publish_at=last_publish_at,
                )
                refreshed = time.monotonic()
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=5)
            except TimeoutError:
                publish_heartbeat(
                    store,
                    provider="finnhub",
                    symbols=subscribed,
                    last_publish_at=last_publish_at,
                )
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            for quote in parse_finnhub_trades(payload):
                try:
                    store.publish(quote)
                    last_publish_at = datetime.now(UTC)
                    metrics.observe(
                        "quotes.provider_latency",
                        quote.freshened(now=last_publish_at).age_seconds,
                    )
                except QuoteStoreError:
                    metrics.increment("quotes.provider_errors")
                    logger.warning(
                        "quote_publish_failed",
                        extra={"ticker": quote.ticker},
                    )


async def stream_finnhub(api_key: str, store: RedisQuoteStore) -> None:
    """Reconnect after a dropped socket. Subscriptions follow watchlists."""
    delay = settings.quote_reconnect_seconds
    while True:
        symbols = load_quote_symbols()
        if not symbols:
            logger.warning("quote_stream_idle", extra={"reason": "no_symbols"})
            await asyncio.sleep(delay)
            continue
        try:
            await _stream_session(api_key, symbols, store)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            get_metrics().increment("quotes.reconnects")
            logger.warning(
                "quote_stream_disconnected",
                extra={"error": type(exc).__name__},
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)
        else:
            delay = settings.quote_reconnect_seconds


def run() -> None:
    setup_logging(settings.log_level)
    source = build_quote_source()
    store = build_worker_store()
    symbols = load_quote_symbols()
    logger.info(
        "quote_worker_started",
        extra={"provider": source.name, "symbols": symbols},
    )
    news = build_news_source()
    if news is not None:
        refresh_news(news, store, symbols)
    if source.name == "alpha_vantage":
        refresh_overviews(source, symbols)
    if source.name == "finnhub":
        key = settings.finnhub_api_key or settings.market_data_api_key
        asyncio.run(stream_finnhub(key, store))
        return
    last_publish_at: datetime | None = None
    while True:
        started = time.monotonic()
        symbols = load_quote_symbols()
        polled_at = datetime.now(UTC)
        metrics = get_metrics()
        metrics.gauge("quotes.active_subscriptions", len(symbols))
        for symbol in symbols:
            try:
                for quote in source.fetch_quotes([symbol]):
                    store.publish(quote)
                    last_publish_at = datetime.now(UTC)
                    metrics.observe(
                        "quotes.provider_latency",
                        quote.freshened(now=last_publish_at).age_seconds,
                    )
            except (ProviderError, QuoteStoreError) as exc:
                metrics.increment("quotes.provider_errors")
                logger.warning(
                    "quote_poll_failed",
                    extra={"ticker": symbol, "error": str(exc)},
                )
        publish_heartbeat(
            store,
            provider=source.name,
            symbols=symbols,
            last_publish_at=last_publish_at,
            last_poll_at=polled_at,
        )
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, settings.quote_poll_seconds - elapsed))


if __name__ == "__main__":
    run()
