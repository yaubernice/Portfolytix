class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.versions: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.counters = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
            "errors": 0,
        }

    def get_json(self, key: str) -> object | None:
        value = self.values.get(key)
        if value is None:
            self.counters["misses"] += 1
            return None
        self.counters["hits"] += 1
        return value

    def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds
        self.counters["sets"] += 1

    def get_version(self, namespace: str) -> int:
        return self.versions.get(namespace, 0)

    def bump_version(self, namespace: str) -> int:
        value = self.get_version(namespace) + 1
        self.versions[namespace] = value
        self.counters["invalidations"] += 1
        return value

    def stats(self) -> dict[str, int | float]:
        hits = self.counters["hits"]
        misses = self.counters["misses"]
        requests = hits + misses
        return {
            **self.counters,
            "requests": requests,
            "hit_rate": hits / requests if requests else 0.0,
        }

    def close(self) -> None:
        return None
