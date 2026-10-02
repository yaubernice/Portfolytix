from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanSample: #represent one execution of the query
    planning_ms: float
    execution_ms: float
    rows: int
    shared_hit_blocks: int
    shared_read_blocks: int
    heap_fetches: int
    nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanSummary:
    runs: int
    planning_ms_median: float
    execution_ms_median: float
    execution_ms_min: float
    execution_ms_max: float
    rows: int
    shared_hit_blocks_median: float
    shared_read_blocks_median: float
    heap_fetches_median: float
    nodes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["nodes"] = list(self.nodes)
        return payload


def parse_explain(payload: object) -> PlanSample:
    # Parse the EXPLAIN output into a PlanSample object.
    """Parse PostgreSQL ``EXPLAIN (..., FORMAT JSON)`` output."""
    document = _unwrap_document(payload) #unwrap the JSON document
    plan = document["Plan"] #get the plan from the document
    nodes = tuple(_walk_nodes(plan)) 
    return PlanSample(
        # Get planning and execution times from the document.
        planning_ms=float(document.get("Planning Time", 0)),
        execution_ms=float(document.get("Execution Time", 0)),
        rows=int(plan.get("Actual Rows", 0)), #get the actual rows from the plan
        # Root plan buffer values represent the whole statement. Summing
        # parent and child values would double-count inherited usage.
        # PostgreSQL found these pages already in memory/cache.
        shared_hit_blocks=int(plan.get("Shared Hit Blocks", 0)),
        # PostgreSQL had to read these pages from storage.
        shared_read_blocks=int(plan.get("Shared Read Blocks", 0)),
        heap_fetches=_sum_metric(plan, "Heap Fetches"),
        nodes=nodes, 
    )


def summarize(samples: list[PlanSample]) -> PlanSummary:
    if not samples:
        raise ValueError("at least one plan sample is required")
    execution = [sample.execution_ms for sample in samples]
    return PlanSummary(
        runs=len(samples),
        planning_ms_median=median(sample.planning_ms for sample in samples), 
        execution_ms_median=median(execution),
        execution_ms_min=min(execution),
        execution_ms_max=max(execution),
        rows=samples[-1].rows,
        shared_hit_blocks_median=median(
            sample.shared_hit_blocks for sample in samples
        ),
        shared_read_blocks_median=median(
            sample.shared_read_blocks for sample in samples
        ),
        heap_fetches_median=median(sample.heap_fetches for sample in samples),
        nodes=samples[-1].nodes,
    )


def percent_change(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return ((after - before) / before) * 100


def _unwrap_document(payload: object) -> dict[str, Any]:
    value = payload
    # psycopg may return JSON as a Python list; some test fixtures retain the
    # SQL row wrapper around that list.
    while isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    # The unwrapped value must be a dictionary containing a Plan key.
    if not isinstance(value, dict) or "Plan" not in value:
        raise ValueError("unexpected EXPLAIN JSON structure")
    return value


def _walk_nodes(plan: dict[str, Any]):
    yield str(plan["Node Type"])
    for child in plan.get("Plans", []):
        yield from _walk_nodes(child)


def _sum_metric(plan: dict[str, Any], key: str) -> int: #sum the metric from the plan
    total = int(plan.get(key, 0))
    for child in plan.get("Plans", []):
        total += _sum_metric(child, key)
    return total
