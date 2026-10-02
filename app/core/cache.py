from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

PENDING_BUMPS = "cache_version_bumps"


class CacheBackend(Protocol):
    def get_json(self, key: str) -> object | None: ...

    def set_json(self, key: str, value: object, ttl_seconds: int) -> None: ...

    def get_version(self, namespace: str) -> int: ...

    def bump_version(self, namespace: str) -> int: ...

    def stats(self) -> dict[str, int | float]: ...

    def close(self) -> None: ...


class NullCache:
    """No-op backend used when caching is disabled."""

    def get_json(self, key: str) -> object | None:
        return None

    def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        return None

    def get_version(self, namespace: str) -> int:
        return 0

    def bump_version(self, namespace: str) -> int:
        return 0

    def stats(self) -> dict[str, int | float]:
        return _stats_payload({})

    def close(self) -> None:
        return None


class RedisCache:
    """JSON cache with Redis-backed versions and aggregate counters.

    Redis failures degrade to cache misses. PostgreSQL remains the source of
    truth, so a cache outage must not turn a valid API read into a 500.
    """

    def __init__(
        self,
        url: str,
        *,
        prefix: str,
        socket_timeout_seconds: float,
    ) -> None:
        self.prefix = prefix.rstrip(":")
        self.client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=socket_timeout_seconds,
            socket_timeout=socket_timeout_seconds,
        )

    def get_json(self, key: str) -> object | None:
        try:
            raw = self.client.get(self._key(key))
            if raw is None:
                self._count("misses")
                logger.info("cache_miss", extra={"cache_key": key})
                return None
            value = json.loads(raw)
            self._count("hits")
            logger.info("cache_hit", extra={"cache_key": key})
            return value
        except (RedisError, json.JSONDecodeError, TypeError):
            self._count("errors")
            logger.warning("cache_read_failed", extra={"cache_key": key})
            return None

    def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        try:
            self.client.set(
                self._key(key),
                json.dumps(value, separators=(",", ":"), sort_keys=True),
                ex=ttl_seconds,
            )
            self._count("sets")
            logger.info(
                "cache_set",
                extra={"cache_key": key, "ttl_seconds": ttl_seconds},
            )
        except (RedisError, TypeError, ValueError):
            self._count("errors")
            logger.warning("cache_write_failed", extra={"cache_key": key})

    def get_version(self, namespace: str) -> int:
        try:
            value = self.client.get(self._version_key(namespace))
            return int(value or 0)
        except (RedisError, TypeError, ValueError):
            self._count("errors")
            logger.warning(
                "cache_version_read_failed",
                extra={"cache_namespace": namespace},
            )
            return 0

    def bump_version(self, namespace: str) -> int:
        try:
            value = int(self.client.incr(self._version_key(namespace)))
            self._count("invalidations")
            logger.info(
                "cache_invalidated",
                extra={"cache_namespace": namespace, "version": value},
            )
            return value
        except (RedisError, TypeError, ValueError):
            self._count("errors")
            logger.warning(
                "cache_invalidation_failed",
                extra={"cache_namespace": namespace},
            )
            return 0

    def stats(self) -> dict[str, int | float]:
        try:
            values = {
                key: int(value)
                for key, value in self.client.hgetall(self._metrics_key()).items()
            }
            return _stats_payload(values)
        except (RedisError, TypeError, ValueError):
            logger.warning("cache_stats_failed")
            return _stats_payload({"errors": 1})

    def close(self) -> None:
        self.client.close()

    def _count(self, metric: str) -> None:
        try:
            self.client.hincrby(self._metrics_key(), metric, 1)
        except RedisError:
            # Metrics are best-effort and must never recurse into error metrics.
            return

    def _key(self, key: str) -> str:
        return f"{self.prefix}:data:{key}"

    def _version_key(self, namespace: str) -> str:
        return f"{self.prefix}:version:{namespace}"

    def _metrics_key(self) -> str:
        return f"{self.prefix}:metrics"


@lru_cache
def get_cache() -> CacheBackend:
    if not settings.cache_enabled:
        return NullCache()
    return RedisCache(
        settings.redis_url,
        prefix=settings.cache_key_prefix,
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
    )


def queue_version_bump(session: Session, namespace: str) -> None:
    """Queue invalidation in the DB transaction; apply it only after commit."""
    pending = session.info.setdefault(PENDING_BUMPS, set())
    pending.add(namespace)


def commit_and_invalidate(session: Session, cache: CacheBackend) -> None:
    """Commit PostgreSQL first, then publish queued Redis version bumps."""
    session.commit()
    pending = session.info.pop(PENDING_BUMPS, set())
    for namespace in sorted(pending):
        cache.bump_version(namespace)


def _stats_payload(values: dict[str, int]) -> dict[str, int | float]:
    hits = values.get("hits", 0)
    misses = values.get("misses", 0)
    requests = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "sets": values.get("sets", 0),
        "invalidations": values.get("invalidations", 0),
        "errors": values.get("errors", 0),
        "requests": requests,
        "hit_rate": hits / requests if requests else 0.0,
    }
