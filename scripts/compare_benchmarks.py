"""Compare two measured Phase 8 JSON benchmark reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.performance.benchmark import percent_change


def main() -> int:
    args = _parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8")) 
    after = json.loads(args.after.read_text(encoding="utf-8"))
    # Ensure the comparison is fair by checking that workloads match.
    _assert_same_workload(before, after)

    # Focus on security_id, timestamp, and adjusted_close.
    before_query = before["projected_history"]
    after_query = after["projected_history"]
    execution_change = percent_change(
        before_query["execution_ms_median"],
        after_query["execution_ms_median"],
    )
    read_change = percent_change(
        before_query["shared_read_blocks_median"],
        after_query["shared_read_blocks_median"],
    )
    heap_change = percent_change(
        before_query["heap_fetches_median"],
        after_query["heap_fetches_median"],
    )

    print(f"{before['label']} → {after['label']}")
    print(
        "execution median: "
        f"{before_query['execution_ms_median']:.3f}ms → "
        f"{after_query['execution_ms_median']:.3f}ms "
        f"({_format_percent(execution_change)})"
    )
    print(
        "shared read blocks median: "
        f"{before_query['shared_read_blocks_median']} → "
        f"{after_query['shared_read_blocks_median']} "
        f"({_format_percent(read_change)})"
    )
    print(
        "heap fetches median: "
        f"{before_query['heap_fetches_median']} → "
        f"{after_query['heap_fetches_median']} "
        f"({_format_percent(heap_change)})"
    )
    print(f"before nodes: {', '.join(before_query['nodes'])}")
    print(f"after nodes: {', '.join(after_query['nodes'])}")
    return 0


def _assert_same_workload(before: dict, after: dict) -> None:
    keys = ("benchmark_price_rows",)
    for key in keys:
        if before["dataset"][key] != after["dataset"][key]:
            raise ValueError(f"dataset mismatch for {key}")
    for key in ("securities", "days", "expected_rows", "measured_runs"):
        if before["query"][key] != after["query"][key]:
            raise ValueError(f"query mismatch for {key}")


def _format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _parse_args() -> argparse.Namespace: #parse the command line arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
