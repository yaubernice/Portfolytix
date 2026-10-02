import pytest

from app.performance.benchmark import parse_explain, percent_change, summarize


def _plan(execution_ms: float, heap_fetches: int = 0):
    return [
        {
            "Plan": {
                "Node Type": "Sort",
                "Actual Rows": 365000,
                "Shared Hit Blocks": 10,
                "Shared Read Blocks": 2,
                "Plans": [
                    {
                        "Node Type": "Index Only Scan",
                        "Actual Rows": 365000,
                        "Shared Hit Blocks": 100,
                        "Shared Read Blocks": 20,
                        "Heap Fetches": heap_fetches,
                    }
                ],
            },
            "Planning Time": 1.25,
            "Execution Time": execution_ms,
        }
    ]


def test_parse_explain_collects_nested_plan_metrics() -> None:
    sample = parse_explain(_plan(42.5, heap_fetches=3))
    assert sample.execution_ms == 42.5
    assert sample.rows == 365000
    assert sample.shared_hit_blocks == 10
    assert sample.shared_read_blocks == 2
    assert sample.heap_fetches == 3
    assert sample.nodes == ("Sort", "Index Only Scan")


def test_summarize_uses_median_not_best_run() -> None:
    summary = summarize(
        [
            parse_explain(_plan(100)),
            parse_explain(_plan(50)),
            parse_explain(_plan(60)),
        ]
    )
    assert summary.runs == 3
    assert summary.execution_ms_median == 60
    assert summary.execution_ms_min == 50
    assert summary.execution_ms_max == 100


def test_summarize_requires_a_sample() -> None:
    with pytest.raises(ValueError, match="at least one"):
        summarize([])


def test_percent_change() -> None:
    assert percent_change(100, 75) == -25
    assert percent_change(0, 10) is None


def test_parse_explain_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        parse_explain({"not": "a plan"})
