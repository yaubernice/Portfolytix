"""Retrieval and calculation checks, kept apart from wording checks.

The cases are a small repeatable set. They do not call a language model.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.ai.evidence import (
    CompanySnapshot,
    HoldingCost,
    build_evidence,
    direct_answer,
    finalize_interpretation,
    portfolio_weighted_roe,
)
from app.ai.openai_compatible import _INTERPRET_INSTRUCTION
from app.schemas.analytics import (
    AllocationOut,
    AnalyticsAssumptions,
    AnalyticsOut,
    SeriesPoint,
)
from app.schemas.common import decimal_to_json

TODAY = date(2026, 10, 21)


def test_largest_holding_comes_from_the_weights() -> None:
    evidence = _evidence([("AAPL", "0.80", "80"), ("MSFT", "0.20", "20")])
    assert _metric(evidence, "largest_weight_ticker")["value"] == "AAPL"
    assert _metric(evidence, "largest_weight")["value"] == "0.8"


def test_largest_holding_answer_names_that_ticker() -> None:
    evidence = _evidence([("AAPL", "0.80", "80"), ("MSFT", "0.20", "20")])
    text = direct_answer("What is my largest holding?", evidence)
    assert text is not None
    assert text.startswith("The largest current weight is AAPL at 0.8.")
    assert "MSFT" not in text.split(".", 1)[0]


def test_allocation_weight_matches_the_stored_share() -> None:
    evidence = _evidence([("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")])
    assert Decimal(_metric(evidence, "weight:AAPL")["value"]) == Decimal("0.25")
    assert Decimal(_metric(evidence, "weight:MSFT")["value"]) == Decimal("0.75")


def test_allocation_answer_quotes_those_weights() -> None:
    evidence = _evidence([("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")])
    text = direct_answer("What is the portfolio allocation?", evidence)
    assert text is not None
    assert "0.25" in text
    assert "0.75" in text
    assert "market value" in text


def test_weighted_roe_is_the_sum_of_weight_times_roe() -> None:
    evidence = _evidence(
        [("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")],
        companies=[
            _company("AAPL", "0.10"),
            _company("MSFT", "0.20"),
        ],
    )
    expected = Decimal("0.25") * Decimal("0.10") + Decimal("0.75") * Decimal("0.20")
    metric = _metric(evidence, "weighted_roe")
    assert Decimal(metric["value"]) == expected
    assert metric["source"] == "calculation"
    assert metric["availability"] == "available"
    assert "AAPL weight 0.25 times ROE 0.1" in metric["method"]
    assert "MSFT weight 0.75 times ROE 0.2" in metric["method"]


def test_weighted_roe_answer_states_the_calculated_result() -> None:
    evidence = _evidence(
        [("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")],
        companies=[_company("AAPL", "0.10"), _company("MSFT", "0.20")],
    )
    expected = decimal_to_json(
        Decimal("0.25") * Decimal("0.10") + Decimal("0.75") * Decimal("0.20")
    )
    text = direct_answer("What is the overall ROE of my portfolio today?", evidence)
    assert text is not None
    assert expected in text
    assert "not a portfolio performance" in text
    assert "not enough daily returns" not in text.lower()
    assert "17.5%" in text


def test_negative_roe_is_kept() -> None:
    evidence = _evidence(
        [("AAPL", "1", "100")],
        companies=[_company("AAPL", "-0.05")],
    )
    assert Decimal(_metric(evidence, "weighted_roe")["value"]) == Decimal("-0.05")


def test_missing_roe_is_not_treated_as_zero() -> None:
    evidence = _evidence(
        [("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")],
        companies=[_company("AAPL", "0.10"), _company("MSFT", None)],
    )
    metric = _metric(evidence, "weighted_roe")
    assert metric["value"] == "unavailable"
    assert metric["availability"] == "unavailable"
    assert metric["value"] != "0"
    assert "MSFT" in metric["method"]
    assert Decimal(_metric(evidence, "roe:AAPL")["value"]) == Decimal("0.1")
    assert _metric(evidence, "roe:MSFT")["availability"] == "unavailable"


def test_missing_roe_answer_names_the_gap_and_not_the_return_history() -> None:
    evidence = _evidence(
        [("AAPL", "0.25", "100"), ("MSFT", "0.75", "300")],
        companies=[_company("AAPL", "0.10"), _company("MSFT", None)],
    )
    text = direct_answer("What is the overall ROE of my portfolio today?", evidence)
    assert text is not None
    lowered = text.lower()
    assert "msft" in lowered
    assert "not treated as zero" in lowered
    assert "not why this figure is missing" in lowered
    assert "not enough daily returns" not in lowered
    assert "0.175" not in text


def test_zero_weight_without_roe_does_not_block_the_average() -> None:
    evidence = _evidence(
        [("AAPL", "1", "100"), ("MSFT", "0", "0")],
        companies=[_company("AAPL", "0.20"), _company("MSFT", None)],
    )
    assert Decimal(_metric(evidence, "weighted_roe")["value"]) == Decimal("0.2")


def test_weights_that_do_not_sum_to_one_are_not_renormalized() -> None:
    allocation = _allocation([("AAPL", "0.20", "20"), ("MSFT", "0.20", "20")])
    result = portfolio_weighted_roe(
        allocation,
        [_company("AAPL", "0.50"), _company("MSFT", "0.50")],
        today=TODAY,
    )
    expected = Decimal("0.20") * Decimal("0.50")
    expected += Decimal("0.20") * Decimal("0.50")
    assert result.value == expected
    evidence = build_evidence(
        _portfolio(allocation),
        [_company("AAPL", "0.50"), _company("MSFT", "0.50")],
        today=TODAY,
    )
    assert "not renormalized" in _metric(evidence, "weighted_roe")["method"]


def test_sharpe_metric_is_undefined_when_returns_are_short() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    assert _metric(evidence, "sharpe_ratio")["value"] == "undefined"
    assert _metric(evidence, "sharpe_ratio")["availability"] == "unavailable"
    assert _metric(evidence, "volatility_change")["value"] == "insufficient_history"


def test_sharpe_answer_blames_return_observations_not_company_roe() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    text = direct_answer("What is my Sharpe ratio?", evidence)
    assert text is not None
    lowered = text.lower()
    assert "not enough daily returns" in lowered
    assert "does not depend on company roe" in lowered
    assert "0.1" not in text


def test_stale_snapshot_keeps_the_figure_and_names_the_date() -> None:
    old = date(2020, 1, 1)
    evidence = _evidence(
        [("AAPL", "1", "100")],
        companies=[_company("AAPL", "0.15", as_of=old)],
        today=TODAY,
    )
    metric = _metric(evidence, "weighted_roe")
    assert Decimal(metric["value"]) == Decimal("0.15")
    assert "2020-01-01" in metric["as_of"]
    text = direct_answer("What is the overall ROE of my portfolio today?", evidence)
    assert text is not None
    assert "2020-01-01" in text
    assert "not a same-day" in text
    assert "more than a year" in text


def test_dividend_income_is_not_replaced_with_another_figure() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    text = direct_answer("What was my dividend income last year?", evidence)
    assert text is not None
    assert "not in the evidence" in text
    assert "0.1" not in text
    assert "110" not in text


def test_unknown_term_is_not_replaced_with_a_portfolio_figure() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    text = direct_answer("What does duration mean?", evidence)
    assert text is not None
    assert "not a stored metric" in text
    assert "0.1" not in text
    assert "time-weighted" not in text.lower()


def test_market_prediction_is_not_given_a_number() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    text = direct_answer("Will the market be higher next year?", evidence)
    assert text is not None
    assert "no forecast is given" in text.lower()
    assert "0.1" not in text
    evidence["direct_answer"] = text
    cleaned = finalize_interpretation("It will rise to 9999 next year.", evidence)
    assert "9999" not in cleaned
    assert "no forecast is given" in cleaned.lower()


def test_news_question_uses_a_stored_headline_only() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    evidence["facts"].append(
        {
            "name": "news:AAPL",
            "value": "Apple reports a supply delay",
            "id": "e50",
            "source": "provider",
        }
    )
    text = direct_answer(
        "any news that might affect my portfolio drastically",
        evidence,
    )
    assert text is not None
    assert "Apple reports a supply delay" in text
    assert "(names a difficult event)" in text
    assert "\nAAPL\n" in f"\n{text}\n"
    assert "0.1" not in text
    empty = direct_answer(
        "what news might affect my portfolio",
        _evidence([("AAPL", "1", "110")]),
    )
    assert empty is not None
    assert "no stored headline" in empty.lower()


def test_news_without_a_bad_event_is_grouped_by_holding() -> None:
    evidence = _evidence([("AAPL", "0.9", "100"), ("AUBN", "0.1", "10")])
    evidence["facts"].extend(
        [
            {
                "name": "news:AAPL",
                "value": "Billionaire Ken Fisher and Jim Cramer Still Like Apple",
                "id": "e41",
                "source": "provider",
            },
            {
                "name": "news:AAPL",
                "value": "Apple vs. Intel: Which Tech Stock Is a Better Buy",
                "id": "e42",
                "source": "provider",
            },
            {
                "name": "news:AUBN",
                "value": "Auburn National Declares Quarterly Dividend",
                "id": "e43",
                "source": "provider",
            },
        ]
    )
    text = direct_answer(
        "any news to show what is bad about my portfolio",
        evidence,
    )
    assert text is not None
    assert "None of the stored headlines" in text
    assert "(names a difficult event)" not in text
    assert "A headline is not a forecast" in text
    lines = text.splitlines()
    assert lines.index("AAPL") < lines.index("AUBN")
    assert sum(line.startswith("- ") for line in lines) == 3
    evidence["direct_answer"] = text
    cleaned = finalize_interpretation(
        "None of the stored headlines name a loss, a lawsuit, "
        "a downgrade, or another bad event. "
        "Should You [e41]. These headlines do not name a loss.",
        evidence,
    )
    assert cleaned.count("Billionaire Ken Fisher") == 1
    assert cleaned.count("None of the stored headlines") == 1
    assert cleaned.count("[e41]") == 1
    assert "do not name a loss" in cleaned


def test_will_it_go_down_today_is_not_a_day_move_recap() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    evidence["metrics"].extend(
        [
            {
                "name": "largest_gainer",
                "value": "AUBN 0.002273",
                "id": "e39",
                "source": "provider",
            },
            {
                "name": "largest_loser",
                "value": "GOOGL -0.03817",
                "id": "e40",
                "source": "provider",
            },
        ]
    )
    text = direct_answer("will my portfolio go down today", evidence)
    assert text is not None
    assert "no forecast is given" in text.lower()
    assert "strongest day move" not in text.lower()
    assert "0.002273" not in text
    assert "tomorrow" not in text.lower()
    evidence["direct_answer"] = text
    cleaned = finalize_interpretation(
        "The strongest day move is AUBN 0.002273.",
        evidence,
    )
    assert "0.002273" not in cleaned
    past = direct_answer("why did my portfolio go down today", evidence)
    assert past is not None
    assert "strongest day move" in past.lower()


def test_industry_structure_is_not_invented() -> None:
    evidence = _evidence(
        [("AAPL", "0.7", "70"), ("GOOGL", "0.3", "30")],
        [
            CompanySnapshot(ticker="AAPL", sector="Technology"),
            CompanySnapshot(ticker="GOOGL", sector="Technology"),
        ],
    )
    evidence["facts"].append(
        {
            "kind": "fact",
            "name": "news:AAPL",
            "value": "Apple faces an antitrust lawsuit",
            "id": "e41",
            "source": "provider",
        }
    )
    evidence["facts"].append(
        {
            "kind": "fact",
            "name": "news:GOOGL",
            "value": "Google declares a dividend",
            "id": "e42",
            "source": "provider",
        }
    )
    question = (
        "Is the industry structurally growing because of aging demographics "
        "or digital transformation, and what is my kill switch?"
    )
    text = direct_answer(question, evidence)
    assert text is not None
    lowered = text.lower()
    assert "not in the stored evidence" in lowered
    assert "aging" not in lowered
    assert "digital" not in lowered
    assert "technology" in lowered
    assert "not a shared supplier" in lowered
    assert "antitrust lawsuit" in lowered
    assert "dividend" not in lowered
    assert "no buy or sell instruction is given" in lowered
    evidence["direct_answer"] = text
    cleaned = finalize_interpretation(
        "Technology is structurally growing because of digital transformation. "
        "You should sell AAPL.",
        evidence,
    )
    assert "digital transformation" not in cleaned.lower()
    assert "should sell" not in cleaned.lower()
    assert "not in the stored evidence" in cleaned.lower()


def test_regulatory_risk_is_not_replaced_by_volatility() -> None:
    evidence = _evidence([("AAPL", "1", "100")])
    text = direct_answer("How high is regulatory risk?", evidence)
    assert text is not None
    assert "not in the stored evidence" in text.lower()
    assert "volatility" not in text.lower()
    still_risk = direct_answer("What is my portfolio risk?", evidence)
    assert still_risk is not None
    assert "not in the stored evidence" not in still_risk.lower()


def test_a_buy_more_question_does_not_give_an_order() -> None:
    evidence = _evidence([("AAPL", "1", "100")])
    text = direct_answer(
        "If the market dropped 20% tomorrow, would you double down "
        "or panic-sell?",
        evidence,
    )
    assert text is not None
    assert "not in the stored evidence" in text.lower()
    assert "no buy or sell instruction is given" in text.lower()
    assert "20" not in text
    assert "tomorrow" not in text.lower()


def test_short_volatility_sample_is_labeled() -> None:
    evidence = _evidence([("AAPL", "1", "100")])
    for item in evidence["metrics"]:
        if item["name"] == "volatility":
            item["value"] = "9.038"
        if item["name"] == "observation_count":
            item["value"] = "5"
    text = direct_answer("What is my volatility?", evidence)
    assert text is not None
    assert "9.038" in text
    assert "5 stored daily returns" in text
    assert "not a long-run risk figure" in text.lower()


def test_invented_evidence_ids_are_removed() -> None:
    evidence = _evidence([("AAPL", "1", "110")])
    real = _metric(evidence, "largest_weight")["id"]
    cleaned = finalize_interpretation(
        f"The largest weight is 1 [{real}]. See [e999] as well.",
        evidence,
    )
    assert f"[{real}]" in cleaned
    assert "[e999]" not in cleaned
    assert "e999" not in cleaned


def test_evidence_and_citations_stay_inside_one_portfolio() -> None:
    apple = _evidence([("AAPL", "1", "110")])
    microsoft = _evidence([("MSFT", "1", "200")])
    apple_blob = json.dumps(apple["facts"] + apple["metrics"])
    microsoft_blob = json.dumps(microsoft["facts"] + microsoft["metrics"])
    assert "MSFT" not in apple_blob
    assert "AAPL" not in microsoft_blob
    answer = direct_answer("What is my largest holding?", apple)
    assert answer is not None
    assert "MSFT" not in answer
    known = {item["id"] for item in apple["facts"] + apple["metrics"]}
    cited = set(re.findall(r"\[(e\d+)\]", answer))
    assert cited
    assert cited <= known


def test_company_snapshot_outside_the_portfolio_is_ignored() -> None:
    evidence = _evidence(
        [("AAPL", "1", "110")],
        companies=[_company("MSFT", "0.90")],
    )
    blob = json.dumps(evidence["facts"] + evidence["metrics"])
    assert "MSFT" not in blob
    assert _metric(evidence, "roe:AAPL")["availability"] == "unavailable"


def test_unrealized_profit_is_price_minus_average_cost() -> None:
    evidence = _evidence(
        [("AAPL", "1", "110")],
        costs=[HoldingCost("AAPL", Decimal("100"))],
    )
    assert Decimal(_metric(evidence, "unrealized_pl")["value"]) == Decimal("10")
    assert _metric(evidence, "average_cost:AAPL")["value"] == "100"


def test_unrealized_answer_does_not_use_return_history() -> None:
    evidence = _evidence(
        [("AAPL", "1", "110")],
        costs=[HoldingCost("AAPL", Decimal("100"))],
    )
    text = direct_answer("What is my unrealized P/L?", evidence)
    assert text is not None
    assert "Unrealized profit is 10." in text
    assert "time-weighted" in text.lower()
    assert "not enough daily returns" not in text.lower()


def test_missing_average_cost_is_not_treated_as_zero() -> None:
    evidence = _evidence(
        [("AAPL", "1", "110")],
        costs=[HoldingCost("AAPL", None)],
    )
    assert _metric(evidence, "unrealized_pl")["value"] == "unavailable"
    text = direct_answer("What is my unrealized profit?", evidence)
    assert text is not None
    assert "not treated as zero" in text.lower()
    assert "not enough daily returns" not in text.lower()
    assert " 0." not in text


def test_interpret_instruction_separates_roe_from_return_history() -> None:
    text = _INTERPRET_INSTRUCTION.lower()
    assert "direct_answer" in text
    assert "company roe" in text
    assert "do not invent an id" in text
    assert "not a portfolio return" in text


def _company(
    ticker: str,
    roe: str | None,
    *,
    as_of: date | None = None,
) -> CompanySnapshot:
    return CompanySnapshot(
        ticker=ticker,
        roe=None if roe is None else Decimal(roe),
        pe_ratio=None if roe is None else Decimal("20"),
        as_of=TODAY if as_of is None and roe is not None else as_of,
    )


def _evidence(
    lines: list[tuple[str, str, str]],
    companies: list[CompanySnapshot] | None = None,
    costs: list[HoldingCost] | None = None,
    *,
    today: date = TODAY,
) -> dict:
    return build_evidence(
        _portfolio(_allocation(lines)),
        companies,
        costs=costs,
        today=today,
    )


def _allocation(lines: list[tuple[str, str, str]]) -> list[AllocationOut]:
    rows = []
    for ticker, weight, market_value in lines:
        value = Decimal(market_value)
        rows.append(
            AllocationOut(
                security_id=uuid4(),
                ticker=ticker,
                quantity=Decimal("1"),
                price=value if value > 0 else Decimal("1"),
                market_value=value,
                weight=Decimal(weight),
            )
        )
    return rows


def _portfolio(allocation: list[AllocationOut]) -> AnalyticsOut:
    returns: list[Decimal | None] = [None, Decimal("0.1")]
    start = date(2024, 1, 1)
    series = [
        SeriesPoint(
            date=start + timedelta(days=index),
            value=Decimal("100"),
            cash_flow=Decimal("0"),
            daily_return=item,
            cumulative_return=item,
        )
        for index, item in enumerate(returns)
    ]
    return AnalyticsOut(
        portfolio_id=uuid4(),
        start_date=series[0].date,
        end_date=series[-1].date,
        observation_count=1,
        total_return=Decimal("0.1"),
        volatility=None,
        sharpe_ratio=None,
        max_drawdown=Decimal("0"),
        allocation=allocation,
        series=series,
        assumptions=AnalyticsAssumptions(
            method="time_weighted",
            price_field="adjusted_close",
            risk_free_rate_annual=Decimal("0.05"),
            trading_days_per_year=252,
            return_frequency="daily",
            volatility="sample",
            sharpe="sharpe",
            max_drawdown="drawdown",
            cash_treatment="no cash sleeve",
            disclaimer="Not investment advice",
        ),
    )


def _metric(evidence: dict, name: str) -> dict:
    for item in evidence["metrics"]:
        if item["name"] == name:
            return item
    raise AssertionError(name)
