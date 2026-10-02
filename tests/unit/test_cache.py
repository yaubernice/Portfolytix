from sqlalchemy.orm import Session

from app.core.cache import (
    PENDING_BUMPS,
    NullCache,
    commit_and_invalidate,
    queue_version_bump,
)
from tests.fakes import FakeCache


def test_null_cache_is_a_safe_miss() -> None:
    cache = NullCache()
    assert cache.get_json("missing") is None
    assert cache.get_version("prices") == 0
    assert cache.bump_version("prices") == 0
    assert cache.stats()["requests"] == 0


def test_version_bumps_are_deduplicated_and_applied_after_commit(
    sqlite_session: Session,
) -> None:
    cache = FakeCache()
    queue_version_bump(sqlite_session, "prices")
    queue_version_bump(sqlite_session, "prices")
    queue_version_bump(sqlite_session, "fundamentals")

    assert cache.get_version("prices") == 0
    assert sqlite_session.info[PENDING_BUMPS] == {"prices", "fundamentals"}

    commit_and_invalidate(sqlite_session, cache)

    assert cache.get_version("prices") == 1
    assert cache.get_version("fundamentals") == 1
    assert PENDING_BUMPS not in sqlite_session.info
    assert cache.stats()["invalidations"] == 2


def test_fake_cache_metrics_include_hit_rate() -> None:
    cache = FakeCache()
    assert cache.get_json("x") is None
    cache.set_json("x", {"ok": True}, 30)
    assert cache.get_json("x") == {"ok": True}

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["sets"] == 1
    assert stats["hit_rate"] == 0.5
