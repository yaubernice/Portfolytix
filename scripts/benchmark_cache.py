"""Measure cold and repeated screening-request latency.

Run this once with CACHE_ENABLED=false and once with it enabled, restarting
the API between runs. A unique offset makes the first enabled request a miss.

    python scripts/benchmark_cache.py --label cache-disabled
    python scripts/benchmark_cache.py --label cache-enabled
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"


def main() -> int:
    args = _parse_args()
    # Offset is part of the cache key. A timestamp avoids reusing an old key.
    payload = {
        "roe_min": "0.15",
        "pe_max": "30",
        "revenue_growth_min": "0.10",
        "offset": int(time.time()),
        "limit": 20,
    }
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        stats_before = _stats(client)
        cold_ms = _request_ms(client, payload)
        warm_ms = [_request_ms(client, payload) for _ in range(args.runs)]
        stats_after = _stats(client)

    result = {
        "label": args.label,
        "recorded_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "runs": args.runs,
        "cold_ms": cold_ms,
        "repeated_ms_median": statistics.median(warm_ms),
        "repeated_ms_min": min(warm_ms),
        "repeated_ms_max": max(warm_ms),
        "stats_before": stats_before,
        "stats_after": stats_after,
        "stats_delta": {
            key: stats_after[key] - stats_before[key]
            for key in ("hits", "misses", "sets", "errors")
        },
    }
    output = args.output or RESULTS_DIR / f"{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote cache benchmark to {output}")
    print(
        f"cold={cold_ms:.3f}ms, "
        f"repeated median={result['repeated_ms_median']:.3f}ms"
    )
    print(f"cache counter delta={result['stats_delta']}")
    return 0


def _request_ms(client: httpx.Client, payload: dict[str, object]) -> float:
    started = time.perf_counter()
    response = client.post("/screen", json=payload)
    elapsed = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return elapsed


def _stats(client: httpx.Client) -> dict[str, int | float]:
    response = client.get("/cache/stats")
    response.raise_for_status()
    return response.json()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18421")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
