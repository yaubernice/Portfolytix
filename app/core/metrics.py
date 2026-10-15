"""Small production-safe operational metrics backend.

Counters and gauges use Redis when caching is enabled so API and worker
processes share one view. Metrics are best effort and never affect requests.
"""

from __future__ import annotations

from functools import lru_cache
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


class OperationalMetrics:
    def increment(self, name: str, amount: int = 1) -> None:
        raise NotImplementedError

    def gauge(self, name: str, value: float) -> None:
        raise NotImplementedError

    def observe(self, name: str, seconds: float) -> None:
        self.increment(f"{name}.count")
        self.gauge(f"{name}.last_seconds", seconds)

    def snapshot(self) -> dict[str, float]:
        raise NotImplementedError


class MemoryMetrics(OperationalMetrics):
    def __init__(self) -> None:
        self._values: dict[str, float] = {}
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._values[name] = self._values.get(name, 0.0) + amount

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._values[name] = float(value)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(sorted(self._values.items()))


class RedisMetrics(OperationalMetrics):
    def __init__(self) -> None:
        self._key = f"{settings.cache_key_prefix.rstrip(':')}:ops:metrics"
        self._client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
        )

    def increment(self, name: str, amount: int = 1) -> None:
        try:
            self._client.hincrby(self._key, name, amount)
        except RedisError:
            return

    def gauge(self, name: str, value: float) -> None:
        try:
            self._client.hset(self._key, name, repr(float(value)))
        except RedisError:
            return

    def snapshot(self) -> dict[str, float]:
        try:
            values = self._client.hgetall(self._key)
            return dict(sorted((key, float(value)) for key, value in values.items()))
        except (RedisError, TypeError, ValueError):
            return {}


@lru_cache
def get_metrics() -> OperationalMetrics:
    if settings.cache_enabled:
        return RedisMetrics()
    return MemoryMetrics()
