from __future__ import annotations

import asyncio
import json
import logging
import queue
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.quotes.models import LiveQuote

logger = logging.getLogger(__name__)


class QuoteStoreError(Exception):
    """Redis could not store or read the current quote."""


class QuoteStore(Protocol):
    def publish(self, quote: LiveQuote) -> None: ...

    def snapshot(self, tickers: list[str] | None = None) -> list[LiveQuote]: ...

    def subscription(self) -> QuoteSubscription: ...

    def put_news(self, ticker: str, items: list[dict]) -> None: ...

    def get_news(self, ticker: str) -> list[dict] | None: ...

    def put_worker_heartbeat(self, heartbeat: dict) -> None: ...

    def get_worker_heartbeat(self) -> dict | None: ...


class QuoteSubscription(Protocol):
    def __aiter__(self) -> AsyncIterator[LiveQuote]: ...

    async def aclose(self) -> None: ...


class MemorySubscription:
    def __init__(self, pending: queue.Queue[LiveQuote | None]) -> None:
        self._pending = pending

    async def __aiter__(self) -> AsyncIterator[LiveQuote]:
        while True:
            item = await asyncio.to_thread(self._pending.get)
            if item is None:
                break
            yield item.freshened()

    async def aclose(self) -> None:
        self._pending.put(None)


class MemoryQuoteStore:
    """In-process quotes for tests and for CACHE_ENABLED=false."""

    def __init__(self) -> None:
        self._quotes: dict[str, LiveQuote] = {}
        self._listeners: list[queue.Queue[LiveQuote | None]] = []
        self._news: dict[str, list[dict]] = {}
        self._heartbeat: dict | None = None

    def publish(self, quote: LiveQuote) -> None:
        self._quotes[quote.ticker] = quote
        for listener in self._listeners:
            listener.put(quote)

    def snapshot(self, tickers: list[str] | None = None) -> list[LiveQuote]:
        if tickers is None:
            rows = list(self._quotes.values())
        else:
            wanted = {ticker.upper() for ticker in tickers}
            rows = [
                quote
                for ticker, quote in self._quotes.items()
                if ticker in wanted
            ]
        return sorted(
            (quote.freshened() for quote in rows),
            key=lambda quote: quote.ticker,
        )

    def subscription(self) -> MemorySubscription:
        pending: queue.Queue[LiveQuote | None] = queue.Queue()
        self._listeners.append(pending)
        return MemorySubscription(pending)

    def put_news(self, ticker: str, items: list[dict]) -> None:
        self._news[ticker.upper()] = items

    def get_news(self, ticker: str) -> list[dict] | None:
        return self._news.get(ticker.upper())

    def put_worker_heartbeat(self, heartbeat: dict) -> None:
        self._heartbeat = dict(heartbeat)

    def get_worker_heartbeat(self) -> dict | None:
        return dict(self._heartbeat) if self._heartbeat is not None else None


class RedisSubscription:
    def __init__(self, client: Redis, pubsub: object, channel: str) -> None:
        self._client = client
        self._pubsub = pubsub
        self._channel = channel

    async def __aiter__(self) -> AsyncIterator[LiveQuote]:
        while True:
            message = await asyncio.to_thread(self._pubsub.get_message, timeout=1.0)
            if not message or message.get("type") != "message":
                continue
            data = message.get("data")
            if not isinstance(data, str):
                continue
            try:
                yield LiveQuote.model_validate_json(data).freshened()
            except ValueError:
                logger.warning(
                    "quote_payload_ignored",
                    extra={"channel": self._channel},
                )

    async def aclose(self) -> None:
        try:
            self._pubsub.close()
        finally:
            self._client.close()


class RedisQuoteStore:
    """Latest quote per ticker, plus a pub/sub channel for live clients.

    Ticks are not written to PostgreSQL. Keys expire with the quote TTL.
    """

    def __init__(
        self,
        url: str,
        *,
        prefix: str,
        ttl_seconds: int,
        socket_timeout_seconds: float,
    ) -> None:
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = ttl_seconds
        self.channel = f"{self.prefix}:live"
        self._url = url
        self._timeout = socket_timeout_seconds
        self.client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=socket_timeout_seconds,
            socket_timeout=socket_timeout_seconds,
        )

    def publish(self, quote: LiveQuote) -> None:
        raw = quote.model_dump_json()
        try:
            self.client.set(self._quote_key(quote.ticker), raw, ex=self.ttl_seconds)
            self.client.publish(self.channel, raw)
        except RedisError as exc:
            raise QuoteStoreError("Could not publish the live quote") from exc

    def snapshot(self, tickers: list[str] | None = None) -> list[LiveQuote]:
        try:
            if tickers is None:
                keys = list(self.client.scan_iter(match=f"{self.prefix}:live:*"))
                raw_rows = self.client.mget(keys) if keys else []
            else:
                raw_rows = self.client.mget(
                    [self._quote_key(ticker) for ticker in tickers]
                )
        except RedisError as exc:
            logger.warning("quote_snapshot_failed", extra={"error": type(exc).__name__})
            return []
        quotes: list[LiveQuote] = []
        for raw in raw_rows:
            if not isinstance(raw, str):
                continue
            try:
                quotes.append(LiveQuote.model_validate_json(raw).freshened())
            except ValueError:
                continue
        return sorted(quotes, key=lambda quote: quote.ticker)

    def subscription(self) -> RedisSubscription:
        client = Redis.from_url(self._url, decode_responses=True, socket_timeout=None)
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self.channel)
        return RedisSubscription(client, pubsub, self.channel)

    def put_news(self, ticker: str, items: list[dict]) -> None:
        try:
            self.client.set(
                self._news_key(ticker),
                json.dumps(items),
                ex=settings.news_ttl_seconds,
            )
        except RedisError as exc:
            raise QuoteStoreError("Could not store news") from exc

    def get_news(self, ticker: str) -> list[dict] | None:
        try:
            raw = self.client.get(self._news_key(ticker))
        except RedisError:
            return None
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(payload, list):
            return None
        return payload

    def put_worker_heartbeat(self, heartbeat: dict) -> None:
        payload = dict(heartbeat)
        payload.setdefault("heartbeat_at", datetime.now(UTC).isoformat())
        try:
            self.client.set(
                self._heartbeat_key(),
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                ex=settings.quote_worker_heartbeat_ttl_seconds,
            )
        except (RedisError, TypeError, ValueError) as exc:
            raise QuoteStoreError("Could not store quote worker heartbeat") from exc

    def get_worker_heartbeat(self) -> dict | None:
        try:
            raw = self.client.get(self._heartbeat_key())
        except RedisError:
            return None
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def _quote_key(self, ticker: str) -> str:
        return f"{self.prefix}:live:{ticker.upper()}"

    def _news_key(self, ticker: str) -> str:
        return f"{self.prefix}:news:{ticker.upper()}"

    def _heartbeat_key(self) -> str:
        return f"{self.prefix}:quote-worker:heartbeat"


def build_quote_store() -> QuoteStore:
    if not settings.cache_enabled:
        return MemoryQuoteStore()
    return RedisQuoteStore(
        settings.redis_url,
        prefix=settings.cache_key_prefix,
        ttl_seconds=settings.quote_ttl_seconds,
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
    )
