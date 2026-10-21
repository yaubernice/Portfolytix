from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.quotes.models import LiveQuote
from app.schemas.analytics import AnalyticsOut
from app.schemas.common import decimal_to_json
from app.services.analytics import annualized_volatility

# About one trading month. Two windows are required before a comparison.
RECENT_WINDOW = 21
# A stored fundamental older than this is still reported, and labeled old.
STALE_AFTER_DAYS = 370
_WEIGHT_TOLERANCE = Decimal("0.01")

_HISTORY_EXCUSE = (
    "not enough daily returns",
    "insufficient history",
    "insufficient historical",
    "historical data",
    "sample window",
    "prior month",
    "prior window",
)
_FORECAST_LEAK = (
    "will rise",
    "will fall",
    "will drop",
    "will climb",
    "guarantee",
    "price target",
    "expected to",
)
_RATIO_NAMES = {
    "weighted_roe",
    "total_return",
    "max_drawdown",
    "latest_daily_return",
    "volatility",
    "recent_volatility",
    "prior_volatility",
}
_RATIO_PREFIXES = ("roe:", "weight:", "day_change:")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_CITE = re.compile(r"\[e(\d+)\]")


@dataclass(frozen=True, slots=True)
class HoldingCost:
    """Average cost for one holding. None means the ledger did not produce one."""

    ticker: str
    average_cost: Decimal | None


@dataclass(frozen=True, slots=True)
class UnrealizedResult:
    value: Decimal | None
    missing: tuple[str, ...]
    inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanySnapshot:
    """One stored fundamental row for a holding. Missing fields stay None."""

    ticker: str
    roe: Decimal | None = None
    pe_ratio: Decimal | None = None
    as_of: date | None = None
    provider: str | None = None
    sector: str | None = None


@dataclass(frozen=True, slots=True)
class WeightedAverage:
    """Market-value-weighted company ROE. None means the average was refused."""

    value: Decimal | None
    missing: tuple[str, ...]
    invalid: tuple[str, ...]
    stale: tuple[str, ...]
    as_of: tuple[str, ...]
    weight_sum: Decimal
    inputs: tuple[str, ...]


def unrealized_profit(
    allocation: list[Any],
    costs: list[HoldingCost],
) -> UnrealizedResult:
    """Market value minus cost. A missing cost is not entered as zero."""
    by_ticker = {row.ticker.upper(): row for row in costs}
    missing: list[str] = []
    inputs: list[str] = []
    total = Decimal("0")
    usable = False
    for line in allocation:
        if line.quantity == 0:
            continue
        cost = by_ticker.get(line.ticker.upper())
        if cost is None or cost.average_cost is None:
            missing.append(line.ticker)
            continue
        gain = (line.price - cost.average_cost) * line.quantity
        total += gain
        usable = True
        inputs.append(
            f"{line.ticker} ({decimal_to_json(line.price)} - "
            f"{decimal_to_json(cost.average_cost)}) "
            f"times {decimal_to_json(line.quantity)}"
        )
    if missing or not usable:
        return UnrealizedResult(None, tuple(missing), tuple(inputs))
    return UnrealizedResult(total, (), tuple(inputs))


def portfolio_weighted_roe(
    allocation: list[Any],
    companies: list[CompanySnapshot],
    *,
    today: date,
) -> WeightedAverage:
    """Sum of weight times company ROE.

    A missing ROE is not entered as zero. Portfolio returns are not an input.
    Equity is not stored, so a bad source denominator cannot be checked here.
    """
    by_ticker = {company.ticker.upper(): company for company in companies}
    missing: list[str] = []
    invalid: list[str] = []
    stale: list[str] = []
    as_of: list[str] = []
    inputs: list[str] = []
    total = Decimal("0")
    weight_sum = Decimal("0")
    usable = False
    for line in allocation:
        weight = line.weight
        if weight == 0:
            continue
        if weight < 0:
            invalid.append(line.ticker)
            continue
        weight_sum += weight
        company = by_ticker.get(line.ticker.upper())
        if company is None or company.roe is None:
            missing.append(line.ticker)
            continue
        total += weight * company.roe
        usable = True
        inputs.append(
            f"{line.ticker} weight {decimal_to_json(weight)} "
            f"times ROE {decimal_to_json(company.roe)}"
        )
        if company.as_of is None or (today - company.as_of).days > STALE_AFTER_DAYS:
            stale.append(line.ticker)
        if company.as_of is not None:
            as_of.append(f"{line.ticker} {company.as_of.isoformat()}")
    if missing or invalid or not usable:
        return WeightedAverage(
            value=None,
            missing=tuple(missing),
            invalid=tuple(invalid),
            stale=tuple(stale),
            as_of=tuple(as_of),
            weight_sum=weight_sum,
            inputs=tuple(inputs),
        )
    return WeightedAverage(
        value=total,
        missing=(),
        invalid=(),
        stale=tuple(stale),
        as_of=tuple(as_of),
        weight_sum=weight_sum,
        inputs=tuple(inputs),
    )


def build_evidence(
    analytics: AnalyticsOut,
    companies: list[CompanySnapshot] | None = None,
    *,
    costs: list[HoldingCost] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Facts and metrics only. This dict is the only context a model may see."""
    as_of_today = today or date.today()
    seq = {"n": 1}
    window = f"{analytics.start_date} to {analytics.end_date}"
    facts: list[dict[str, str]] = [
        _item(
            "fact",
            "metric_scope",
            (
                "Company ratios such as ROE come from stored fundamentals. "
                "Portfolio return, volatility, Sharpe, and drawdown come from "
                "daily portfolio observations. One cannot fill in for the other."
            ),
            "calculation",
            seq=seq,
            method=(
                "Labels which family a figure belongs to. "
                "It is not itself a portfolio result."
            ),
        ),
        _item(
            "fact",
            "sample_window",
            window,
            "database",
            seq=seq,
            as_of=window,
            method=(
                "Dates of the stored daily series used for portfolio returns. "
                "Not used for company ROE."
            ),
        ),
        _item(
            "fact",
            "allocation_history",
            "not stored; current weights only",
            "database",
            seq=seq,
            method="Only the current weights are stored.",
        ),
    ]
    weights: list[dict[str, str]] = []
    market_total = Decimal("0")
    for line in analytics.allocation:
        market_total += line.market_value
        facts.append(
            _item(
                "fact",
                f"position:{line.ticker}",
                (
                    f"{line.ticker} quantity {decimal_to_json(line.quantity)} "
                    f"latest price {decimal_to_json(line.price)}"
                ),
                "database",
                seq=seq,
                method=(
                    "Quantity from stored transactions and the latest price "
                    "used for this portfolio."
                ),
            )
        )
        weights.append(
            _item(
                "metric",
                f"weight:{line.ticker}",
                decimal_to_json(line.weight),
                "calculation",
                seq=seq,
                method=(
                    "This holding's market value divided by the portfolio "
                    "market value. 1 means the whole portfolio."
                ),
            )
        )
        weights.append(
            _item(
                "metric",
                f"market_value:{line.ticker}",
                decimal_to_json(line.market_value),
                "calculation",
                seq=seq,
                unit="USD",
                method="Quantity times the latest price used for this portfolio.",
            )
        )

    returns = [
        point.daily_return
        for point in analytics.series
        if point.daily_return is not None
    ]
    comparison = _compare_volatility(
        returns,
        analytics.assumptions.trading_days_per_year,
    )
    largest = _largest_weight(analytics)
    rate = decimal_to_json(analytics.assumptions.risk_free_rate_annual)
    metrics = [
        _item(
            "metric",
            "total_return",
            _num(analytics.total_return),
            "calculation",
            seq=seq,
            as_of=window,
            method=(
                "Time-weighted return over stored daily closes. "
                "Cash flows are removed. Not company ROE."
            ),
        ),
        _item(
            "metric",
            "volatility",
            _num(analytics.volatility),
            "calculation",
            seq=seq,
            method=(
                "Annualized sample standard deviation of daily returns, "
                "using the square root of 252. Needs at least two daily "
                "returns. Undefined is not zero."
            ),
        ),
        _item(
            "metric",
            "sharpe_ratio",
            _num(analytics.sharpe_ratio),
            "calculation",
            seq=seq,
            method=(
                "Average excess return divided by the standard deviation of "
                f"daily returns. The stored annual risk-free rate is {rate}. "
                "Undefined when fewer than two daily returns exist, or when "
                "volatility is zero."
            ),
        ),
        _item(
            "metric",
            "max_drawdown",
            _num(analytics.max_drawdown),
            "calculation",
            seq=seq,
            method=(
                "Largest peak-to-trough decline of the time-weighted "
                "wealth index. A value of 0 is a measured result."
            ),
        ),
        _item(
            "metric",
            "observation_count",
            str(analytics.observation_count),
            "calculation",
            seq=seq,
            method="How many daily portfolio returns are stored.",
        ),
        _item(
            "metric",
            "recent_volatility",
            _num(comparison["recent"]),
            "calculation",
            seq=seq,
            method="Annualized volatility over the latest 21 daily returns.",
        ),
        _item(
            "metric",
            "prior_volatility",
            _num(comparison["prior"]),
            "calculation",
            seq=seq,
            method="Annualized volatility over the 21 daily returns before that.",
        ),
        _item(
            "metric",
            "volatility_change",
            str(comparison["change"]),
            "calculation",
            seq=seq,
            method=(
                "Compares the latest 21 daily returns with the 21 before them. "
                "Insufficient history means those windows are not both available."
            ),
        ),
        _item(
            "metric",
            "largest_weight_ticker",
            largest[0],
            "calculation",
            seq=seq,
            method="Ticker of the holding with the highest current weight.",
        ),
        _item(
            "metric",
            "largest_weight",
            largest[1],
            "calculation",
            seq=seq,
            method="The highest current portfolio weight.",
        ),
        _item(
            "metric",
            "latest_daily_return",
            _latest_daily_return(analytics),
            "calculation",
            seq=seq,
            method="The last daily portfolio return in the stored series.",
        ),
        _item(
            "metric",
            "portfolio_market_value",
            decimal_to_json(market_total),
            "calculation",
            seq=seq,
            unit="USD",
            method="Sum of holding market values. There is no cash sleeve.",
        ),
    ]
    fundamental_items: list[dict[str, str]] = []
    if companies is not None and analytics.allocation:
        fundamental_items = _fundamental_items(
            analytics,
            companies,
            today=as_of_today,
            seq=seq,
        )
    cost_items: list[dict[str, str]] = []
    if costs is not None and analytics.allocation:
        cost_items = _cost_items(analytics, costs, seq=seq)
    company_facts = [item for item in fundamental_items if item["kind"] == "fact"]
    company_metrics = [item for item in fundamental_items if item["kind"] != "fact"]
    return {
        "facts": facts + company_facts,
        "metrics": company_metrics + cost_items + weights + metrics,
        "evidence_date": as_of_today.isoformat(),
    }


def _cost_items(
    analytics: AnalyticsOut,
    costs: list[HoldingCost],
    *,
    seq: dict[str, int],
) -> list[dict[str, str]]:
    by_ticker = {row.ticker.upper(): row for row in costs}
    items: list[dict[str, str]] = []
    for line in analytics.allocation:
        cost = by_ticker.get(line.ticker.upper())
        if cost is None or cost.average_cost is None:
            items.append(
                _item(
                    "metric",
                    f"average_cost:{line.ticker}",
                    "unavailable",
                    "unavailable",
                    seq=seq,
                    unit="USD",
                    availability="unavailable",
                    method=(
                        "No average cost is stored for this holding. "
                        "A short return history is not the reason."
                    ),
                )
            )
            continue
        items.append(
            _item(
                "metric",
                f"average_cost:{line.ticker}",
                decimal_to_json(cost.average_cost),
                "calculation",
                seq=seq,
                unit="USD",
                method=(
                    "Average cost of the shares still held, from stored buys and sells."
                ),
            )
        )
    result = unrealized_profit(analytics.allocation, costs)
    if result.value is None:
        why = (
            "Not calculated. Missing average cost is not treated as zero. "
            "Portfolio return history is not an input."
        )
        if result.missing:
            why = f"{why} No average cost for {', '.join(result.missing)}."
        items.append(
            _item(
                "metric",
                "unrealized_pl",
                "unavailable",
                "unavailable",
                seq=seq,
                unit="USD",
                availability="unavailable",
                method=why,
            )
        )
        return items
    note = (
        "Sum of (latest price minus average cost) times quantity. "
        "Missing cost is not treated as zero. This is not a time-weighted "
        "return."
    )
    if result.inputs:
        note = f"{note} Inputs: {'; '.join(result.inputs)}."
    items.append(
        _item(
            "metric",
            "unrealized_pl",
            decimal_to_json(result.value),
            "calculation",
            seq=seq,
            unit="USD",
            method=note,
        )
    )
    return items


def _fundamental_items(
    analytics: AnalyticsOut,
    companies: list[CompanySnapshot],
    *,
    today: date,
    seq: dict[str, int],
) -> list[dict[str, str]]:
    by_ticker = {company.ticker.upper(): company for company in companies}
    items: list[dict[str, str]] = []
    for line in analytics.allocation:
        company = by_ticker.get(line.ticker.upper())
        items.extend(_company_items(line.ticker, company, seq=seq))
    weighted = portfolio_weighted_roe(analytics.allocation, companies, today=today)
    items.append(_weighted_item(weighted, seq=seq))
    return items


def _company_items(
    ticker: str,
    company: CompanySnapshot | None,
    *,
    seq: dict[str, int],
) -> list[dict[str, str]]:
    snapshot = "Stored company snapshot."
    if company and company.provider and company.provider != "seed":
        snapshot = f"Stored company snapshot from {company.provider}."
    as_of = ""
    if company and company.as_of is not None:
        as_of = company.as_of.isoformat()
    if company is None or company.roe is None:
        roe_item = _item(
            "metric",
            f"roe:{ticker}",
            "unavailable",
            "unavailable",
            seq=seq,
            availability="unavailable",
            method=(
                "No fundamental snapshot is stored for this holding. "
                "This is not caused by a short portfolio return history."
            ),
        )
    else:
        roe_item = _item(
            "metric",
            f"roe:{ticker}",
            decimal_to_json(company.roe),
            "database",
            seq=seq,
            as_of=as_of,
            method=(
                f"{snapshot} The value is a decimal ratio, not a percent. "
                "Equity is not stored separately, so the denominator "
                "cannot be checked."
            ),
        )
    if company is None or company.pe_ratio is None:
        pe_item = _item(
            "metric",
            f"pe:{ticker}",
            "unavailable",
            "unavailable",
            seq=seq,
            availability="unavailable",
            method=(
                "No stored price-to-earnings multiple for this holding. "
                "Portfolio return history is not a substitute."
            ),
        )
    else:
        pe_item = _item(
            "metric",
            f"pe:{ticker}",
            decimal_to_json(company.pe_ratio),
            "database",
            seq=seq,
            as_of=as_of,
            method=f"{snapshot} A company multiple, not a portfolio return.",
        )
    items = [roe_item, pe_item]
    sector = (company.sector or "").strip() if company else ""
    if sector:
        items.append(
            _item(
                "fact",
                f"sector:{ticker}",
                sector,
                "database",
                seq=seq,
                method=(
                    "Sector label stored on the security. "
                    "Not a growth rate, a supplier, or a forecast."
                ),
            )
        )
    return items


def _weighted_item(weighted: WeightedAverage, *, seq: dict[str, int]) -> dict[str, str]:
    dates = ", ".join(weighted.as_of)
    if weighted.value is None:
        why = _weighted_gap(weighted)
        return _item(
            "metric",
            "weighted_roe",
            "unavailable",
            "unavailable",
            seq=seq,
            availability="unavailable",
            as_of=dates,
            method=why,
        )
    note = (
        "Sum of each holding's portfolio weight times that company's stored ROE. "
        "Missing ROE is not treated as zero. "
        "Equity is not stored separately, so a bad source denominator cannot "
        "be checked. This is a summary of company ratios, not a portfolio return."
    )
    if weighted.inputs:
        note = f"{note} Inputs: {'; '.join(weighted.inputs)}."
    if abs(weighted.weight_sum - Decimal("1")) > _WEIGHT_TOLERANCE:
        note = (
            f"{note} Stored weights sum to {decimal_to_json(weighted.weight_sum)}, "
            "not 1. They are not renormalized."
        )
    if weighted.stale:
        note = (
            f"{note} Snapshots older than a year: {', '.join(weighted.stale)}. "
            "The figure is not a same-day measure."
        )
    return _item(
        "metric",
        "weighted_roe",
        decimal_to_json(weighted.value),
        "calculation",
        seq=seq,
        as_of=dates,
        method=note,
    )


def _weighted_gap(weighted: WeightedAverage) -> str:
    parts = [
        "Not calculated. Missing company ROE is not treated as zero. "
        "Portfolio return history is not an input."
    ]
    if weighted.missing:
        parts.append(f"No stored ROE for {', '.join(weighted.missing)}.")
    if weighted.invalid:
        parts.append(f"Negative weight for {', '.join(weighted.invalid)}.")
    if not weighted.missing and not weighted.invalid:
        parts.append("No holding has a positive portfolio weight.")
    if weighted.inputs:
        parts.append(f"ROE that is stored: {'; '.join(weighted.inputs)}.")
    return " ".join(parts)


def attach_live_moves(
    evidence: dict[str, Any],
    analytics: AnalyticsOut,
    quotes: list[LiveQuote],
) -> dict[str, Any]:
    """Add day-change metrics from live quotes. Missing quotes add nothing."""
    seq = _resume(evidence)
    by_ticker = {quote.ticker: quote for quote in quotes}
    moves: list[tuple[str, Decimal]] = []
    for line in analytics.allocation:
        quote = by_ticker.get(line.ticker)
        if quote is None or quote.change_percent is None:
            continue
        moves.append((line.ticker, quote.change_percent))
        stamp = quote.provider_timestamp or quote.timestamp
        evidence["metrics"].append(
            _item(
                "metric",
                f"day_change:{line.ticker}",
                decimal_to_json(quote.change_percent),
                "provider",
                seq=seq,
                as_of=stamp.date().isoformat(),
                method=_quote_method(quote),
            )
        )
    if not moves:
        return evidence
    gainer = max(moves, key=lambda item: item[1])
    loser = min(moves, key=lambda item: item[1])
    evidence["metrics"].append(
        _item(
            "metric",
            "largest_gainer",
            f"{gainer[0]} {decimal_to_json(gainer[1])}",
            "calculation",
            seq=seq,
            method="Largest provider day change among current holdings.",
        )
    )
    evidence["metrics"].append(
        _item(
            "metric",
            "largest_loser",
            f"{loser[0]} {decimal_to_json(loser[1])}",
            "calculation",
            seq=seq,
            method="Smallest provider day change among current holdings.",
        )
    )
    return evidence


def render_interpretation(evidence: dict[str, Any]) -> str:
    """Template wording. Every number is copied from evidence."""
    metrics = {item["name"]: item["value"] for item in evidence["metrics"]}
    positions = [
        item["value"]
        for item in evidence["facts"]
        if item["name"].startswith("position:")
    ]
    change = metrics["volatility_change"]
    if change == "insufficient_history":
        first = (
            "There are not enough daily returns to compare this month "
            "with the prior month."
        )
    elif change == "increased":
        first = (
            f"Recent annualized volatility is {metrics['recent_volatility']}, "
            f"above the prior window {metrics['prior_volatility']}."
        )
    elif change == "decreased":
        first = (
            f"Recent annualized volatility is {metrics['recent_volatility']}, "
            f"below the prior window {metrics['prior_volatility']}."
        )
    else:
        first = (
            f"Recent annualized volatility is {metrics['recent_volatility']}, "
            "the same as the prior window."
        )
    volatility = metrics["volatility"]
    volatility_text = "undefined." if volatility == "undefined" else f"{volatility}."
    holdings = (
        "Current holdings: " + "; ".join(positions) + "."
        if positions
        else "No current holdings are stored."
    )
    sentences = [
        first,
        f"Full-sample total return is {metrics['total_return']}.",
        f"Full-sample annualized volatility is {volatility_text}",
        holdings,
        "Historical allocation is not stored, so an allocation change is not measured.",
        (
            f"The largest current weight is {metrics['largest_weight_ticker']} "
            f"at {metrics['largest_weight']}."
        ),
        f"The latest daily return in the sample is {metrics['latest_daily_return']}.",
    ]
    if "largest_gainer" in metrics:
        sentences.append(f"The strongest day move is {metrics['largest_gainer']}.")
        sentences.append(f"The weakest day move is {metrics['largest_loser']}.")
    return " ".join(sentences)


def direct_answer(question: str, evidence: dict[str, Any]) -> str | None:
    """Deterministic answer for questions the evidence can settle."""
    text = " ".join(question.lower().split())
    if _mentions(text, "news", "headline", "story", "stories"):
        return _news_answer(evidence)
    if _is_ungrounded(text):
        return _limits_answer(evidence)
    if _is_forecast(text):
        return _outlook_answer(evidence)
    if _mentions(text, "roe") or "return on equity" in text:
        return _roe_answer(evidence)
    if "p/e" in text or _mentions(text, "pe") or "price to earnings" in text:
        return _pe_answer(evidence)
    if _mentions(text, "sharpe"):
        return _sharpe_answer(evidence)
    if _mentions(text, "drawdown"):
        return _drawdown_answer(evidence)
    if _mentions(text, "volatility", "risk"):
        return _volatility_answer(evidence)
    if (
        "unrealized" in text
        or "p/l" in text
        or "p&l" in text
        or "profit and loss" in text
    ):
        return _unrealized_answer(evidence)
    if _mentions(text, "largest", "biggest", "concentration"):
        return _largest_answer(evidence)
    if _mentions(text, "allocation", "allocated", "percentage", "weight"):
        return _allocation_answer(evidence, text)
    if _mentions(text, "today", "gainer", "loser", "mover") or "day move" in text:
        return _day_answer(evidence)
    if _mentions(text, "summarize", "summary", "overview"):
        return _summary_answer(evidence)
    if _mentions(text, "return", "performance") or "how did" in text:
        return _return_answer(evidence)
    if _mentions(text, "holding", "holdings", "positions"):
        return _holdings_answer(evidence)
    absent = _absent_fact(text)
    if absent:
        return absent
    if re.search(r"\b(what is|what does|define|meaning)\b", text):
        return (
            "That phrase is not a stored metric, so no other figure is used "
            "in its place."
        )
    return None


def finalize_interpretation(text: str, evidence: dict[str, Any]) -> str:
    """Drop invented citations and numbers the evidence does not support."""
    direct = scrub_citations(str(evidence.get("direct_answer") or "").strip(), evidence)
    body = scrub_citations(text.strip(), evidence)
    if direct and _same_words(body, direct):
        return direct
    if direct and _closed(direct):
        return direct
    allowed = _allowed_numbers(evidence)
    _add_numbers(direct, allowed)
    extra = _safe_extra(body, direct, allowed)
    if "\n" in direct:
        extra = _without_repeated_headlines(extra, direct, evidence)
    if not direct:
        return extra or ("The evidence does not establish a figure for that question.")
    if not extra or extra in direct or _same_words(extra, direct):
        return direct
    if direct in extra:
        return extra
    return f"{direct}\n\n{extra}"


def scrub_citations(text: str, evidence: dict[str, Any]) -> str:
    """Remove [eN] citations that were not in the evidence given to the model."""
    allowed = {
        item.get("id")
        for item in [*evidence.get("facts", []), *evidence.get("metrics", [])]
        if item.get("id")
    }

    def replace(match: re.Match[str]) -> str:
        token = f"e{match.group(1)}"
        if token in allowed:
            return match.group(0)
        return ""

    cleaned = _CITE.sub(replace, text)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _roe_answer(evidence: dict[str, Any]) -> str:
    weighted = _find(evidence, "weighted_roe")
    company_rows = [
        item for item in evidence.get("metrics", []) if item["name"].startswith("roe:")
    ]
    if weighted is None and not company_rows:
        return (
            "Company ROE is not in this evidence. "
            "Return on equity is a company figure: net income divided by "
            "shareholder equity. A market-value-weighted average of those "
            "company ratios would be a summary of the holdings, not a portfolio "
            "performance number. Portfolio performance history is not required "
            "to retrieve company ROE, and it is not used as a substitute."
        )
    if weighted and weighted.get("availability") == "available":
        return _roe_ready(evidence, weighted)
    missing = [
        item["name"].split(":", 1)[1]
        for item in company_rows
        if item.get("availability") == "unavailable"
    ]
    present = [
        f"{item['name'].split(':', 1)[1]} {item['value']}{_cite(item)}"
        for item in company_rows
        if item.get("availability") == "available"
    ]
    names = ", ".join(missing) or "one or more holdings"
    stored = ""
    if present:
        stored = f" ROE is stored for {', '.join(present)}."
    return (
        f"A market-value-weighted average ROE is not available because "
        f"company ROE is missing for {names}.{stored}\n\n"
        "Missing company figures are not treated as zero. "
        "Return on equity is net income divided by shareholder equity. "
        "It does not use portfolio performance history, so that history "
        "is not why this figure is missing. "
        "A stored ROE is required for every holding with a positive weight."
    )


def _roe_ready(evidence: dict[str, Any], weighted: dict[str, str]) -> str:
    value = weighted["value"]
    percent = _percent_text(value)
    dates = weighted.get("as_of") or ""
    today = str(evidence.get("evidence_date") or "")
    timing = ""
    if dates:
        timing = f" The stored snapshot is as of {dates}."
        snapshot_dates = re.findall(r"\d{4}-\d{2}-\d{2}", dates)
        if today and any(day != today for day in snapshot_dates):
            timing += " This is not a same-day figure."
        if "older than a year" in weighted.get("method", ""):
            timing += " At least one snapshot is more than a year old."
    inputs = ""
    method = weighted.get("method", "")
    marker = "Inputs: "
    if marker in method:
        inputs = " " + method[method.index(marker) :].split(" Stored weights")[0]
        if "Snapshots older" in inputs:
            inputs = inputs.split(" Snapshots older")[0]
    return (
        f"The market-value-weighted average ROE of these companies is "
        f"{value}, which means {percent}.{_cite(weighted)}\n\n"
        "Each holding's portfolio weight is multiplied by that company's ROE, "
        "then added up. This is a summary of company ratios, not a portfolio "
        f"performance number.{inputs}{timing}"
    )


def _pe_answer(evidence: dict[str, Any]) -> str:
    items = [
        item for item in evidence.get("metrics", []) if item["name"].startswith("pe:")
    ]
    if not items:
        return (
            "Company price-to-earnings is not in this evidence. "
            "It is a company multiple, not a portfolio return, and portfolio "
            "performance history is not a substitute."
        )
    present = [
        f"{item['name'].split(':', 1)[1]} {item['value']}{_cite(item)}"
        for item in items
        if item.get("availability") == "available"
    ]
    missing = [
        item["name"].split(":", 1)[1]
        for item in items
        if item.get("availability") == "unavailable"
    ]
    text = (
        "No portfolio P/E is calculated. P/E is a company multiple and is not "
        "added across holdings."
    )
    if present:
        text += " Stored P/E: " + "; ".join(present) + "."
    if missing:
        text += (
            f" P/E is missing for {', '.join(missing)}, and those holdings "
            "are not treated as zero."
        )
    return text


def _sharpe_answer(evidence: dict[str, Any]) -> str:
    item = _find(evidence, "sharpe_ratio")
    if item is None or item["value"] in {"undefined", "unavailable"}:
        count = _find(evidence, "observation_count")
        stored = f" ({count['value']} stored)" if count else ""
        return (
            "The Sharpe ratio is unavailable because there are not enough "
            f"daily returns{stored}. At least two daily returns are required, "
            "and it is also undefined when volatility is zero. "
            "Unavailable is not zero. This does not depend on company ROE."
        )
    return (
        f"The Sharpe ratio is {item['value']}.{_cite(item)} "
        "It compares average portfolio return with how much that return "
        "bounced around. It is not a company fundamental."
    )


def _drawdown_answer(evidence: dict[str, Any]) -> str:
    item = _find(evidence, "max_drawdown")
    if item is None or item["value"] in {"undefined", "unavailable"}:
        return (
            "Maximum drawdown is unavailable because the stored return series "
            "is too short to measure a peak and a later trough. "
            "This uses portfolio returns, not company ROE. Unavailable is not zero."
        )
    return (
        f"Maximum drawdown is {item['value']}.{_cite(item)}\n\n"
        "This is the largest peak-to-trough decline of the time-weighted "
        "wealth index. A value of 0 is a measured result, not a missing figure."
    )


def _volatility_answer(evidence: dict[str, Any]) -> str:
    summary = render_interpretation(evidence)
    first = summary.split(". ")[0]
    if not first.endswith("."):
        first += "."
    change = _find(evidence, "volatility_change")
    if change and change["value"] == "insufficient_history":
        text = (
            f"{first} This limit is the number of daily portfolio returns, "
            "not a missing company fundamental."
        )
        item = _find(evidence, "volatility")
        if item and item.get("value") not in {"undefined", "unavailable"}:
            text = f"{text} {_volatility_sentence(item, evidence)}"
        return text
    return first + _cite(change)


def _unrealized_answer(evidence: dict[str, Any]) -> str:
    total = _find(evidence, "unrealized_pl")
    if total is None:
        return (
            "Unrealized profit is not calculated because each holding's cost "
            "is not in this evidence. A missing cost is not treated as zero, "
            "and it is not the same limit as a short return history. "
            "Cost for each open holding is required."
        )
    if total.get("availability") == "available":
        return (
            f"Unrealized profit is {total['value']}.{_cite(total)}\n\n"
            "This is the latest price minus average cost, multiplied by the "
            "shares still held, then added across holdings. It is not a "
            "time-weighted return and it does not use company ROE."
        )
    missing = [
        item["name"].split(":", 1)[1]
        for item in evidence.get("metrics", [])
        if item["name"].startswith("average_cost:")
        and item.get("availability") == "unavailable"
    ]
    names = ", ".join(missing) or "one or more holdings"
    return (
        f"Unrealized profit is not available because average cost is missing "
        f"for {names}. Missing cost is not treated as zero. A short return "
        "history is not the reason. Average cost from stored buys and sells "
        "is required."
    )


def _largest_answer(evidence: dict[str, Any]) -> str:
    ticker = _find(evidence, "largest_weight_ticker")
    weight = _find(evidence, "largest_weight")
    if ticker is None or ticker["value"] == "undefined":
        return "No position weight is stored."
    amount = weight["value"] if weight else "undefined"
    return (
        f"The largest current weight is {ticker['value']} at {amount}.{_cite(weight)}"
    )


def _allocation_answer(evidence: dict[str, Any], text: str) -> str:
    weights = [
        item
        for item in evidence.get("metrics", [])
        if item["name"].startswith("weight:")
    ]
    named = []
    for item in weights:
        ticker = item["name"].split(":", 1)[1]
        if re.search(rf"\b{re.escape(ticker.lower())}\b", text):
            named.append(item)
    chosen = named or weights
    if not chosen:
        return "No current allocation is stored."
    parts = [
        (
            f"{item['name'].split(':', 1)[1]} is {item['value']} "
            f"of portfolio market value{_cite(item)}"
        )
        for item in chosen
    ]
    return (
        "Current allocation is market value divided by total market value. "
        + ". ".join(parts)
        + ". Past allocation is not stored, so a change in mix is not measured."
    )


def _outlook_answer(evidence: dict[str, Any]) -> str:
    """A future period is not a stored result. Say what is stored instead."""
    sentences = [
        "No forecast is given, and no future return is stated.",
        "A past day move is not a prediction, and a delayed print is not a live tape.",
    ]
    largest = _find(evidence, "largest_weight")
    ticker = _find(evidence, "largest_weight_ticker")
    weight = largest.get("value") if largest else ""
    if ticker and weight not in {"", "undefined", "unavailable"}:
        sentences.append(
            f"The largest current weight is {ticker['value']} at {largest['value']}."
            f"{_cite(largest)}"
        )
    headlines = _headlines(evidence)
    if headlines:
        sentences.append(f"Stored headlines: {'; '.join(headlines)}.")
    else:
        sentences.append("No stored headline is available for the current holdings.")
    return " ".join(sentences)


_ADVERSE_EVENT = re.compile(
    r"\b("
    r"lawsuit|lawsuits|sued|downgrade|downgraded|downgrades|"
    r"recall|recalled|bankruptcy|bankrupt|fraud|"
    r"investigation|investigated|probe|"
    r"layoff|layoffs|penalty|penalties|"
    r"default|defaults|defaulted|"
    r"missed|misses|shortage|shortages|"
    r"delay|delays|delayed|"
    r"decline|declines|declined|declining|"
    r"drop|drops|dropped|loss|losses|"
    r"warning|warns|warned|"
    r"disappoints|disappointed|disappointing|"
    r"crash|crashed|scandal|weakness"
    r")\b",
    re.IGNORECASE,
)


def _news_answer(evidence: dict[str, Any]) -> str:
    groups = _headline_groups(evidence)
    if not groups:
        return (
            "No stored headline is available for the current holdings. "
            "A missing headline is not treated as a price move."
        )
    marked = sum(
        1
        for _, items in groups
        for item in items
        if _names_adverse_event(str(item.get("value", "")))
    )
    if marked == 0:
        finding = (
            "None of the stored headlines name a loss, a lawsuit, "
            "a downgrade, or another bad event."
        )
    elif marked == 1:
        finding = "One stored headline names a difficult event."
    else:
        finding = "Some stored headlines name a difficult event."
    lines = [
        finding,
        "",
        "A headline is not a forecast of a future move.",
        "",
    ]
    for ticker, items in groups:
        lines.append(ticker)
        for item in items:
            note = ""
            if _names_adverse_event(str(item.get("value", ""))):
                note = " (names a difficult event)"
            lines.append(f"- {item['value']}{_cite(item)}{note}")
        lines.append("")
    return "\n".join(lines).strip()


def _headline_groups(
    evidence: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    index: dict[str, list[dict[str, Any]]] = {}
    for item in evidence.get("facts", []):
        name = str(item.get("name", ""))
        if not name.startswith("news:"):
            continue
        ticker = name.split(":", 1)[1]
        bucket = index.get(ticker)
        if bucket is None:
            bucket = []
            index[ticker] = bucket
            groups.append((ticker, bucket))
        bucket.append(item)
    return groups


def _names_adverse_event(headline: str) -> bool:
    return _ADVERSE_EVENT.search(headline) is not None


def _headlines(evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in evidence.get("facts", []):
        name = str(item.get("name", ""))
        if not name.startswith("news:"):
            continue
        ticker = name.split(":", 1)[1]
        lines.append(f"{ticker}: {item['value']}{_cite(item)}")
    return lines


def attach_headlines(
    evidence: dict[str, Any],
    headlines: list[tuple[str, str]],
) -> dict[str, Any]:
    """Add provider headlines already fetched for these holdings."""
    seq = _resume(evidence)
    for ticker, headline in headlines[:8]:
        evidence["facts"].append(
            _item(
                "fact",
                f"news:{ticker}",
                headline,
                "provider",
                seq=seq,
                label=f"{ticker} headline",
                method="Provider headline stored for this holding. Not a forecast.",
            )
        )
    return evidence


def _day_answer(evidence: dict[str, Any]) -> str:
    gainer = _find(evidence, "largest_gainer")
    loser = _find(evidence, "largest_loser")
    if gainer is None or loser is None:
        return (
            "No day move is stored. A portfolio return over the stored history "
            "is a different figure and is not used as today's move."
        )
    moves = [
        item
        for item in evidence.get("metrics", [])
        if item["name"].startswith("day_change:")
    ]
    return (
        f"The strongest day move is {gainer['value']}.{_cite(gainer)} "
        f"The weakest day move is {loser['value']}.{_cite(loser)} "
        f"{_freshness(moves, str(evidence.get('evidence_date') or ''))}"
    )


def _summary_answer(evidence: dict[str, Any]) -> str:
    parts = [
        _largest_answer(evidence),
        _return_answer(evidence),
    ]
    volatility = _find(evidence, "volatility")
    if volatility and volatility["value"] in {"undefined", "unavailable"}:
        parts.append(
            "Annualized volatility is unavailable because there are not enough "
            "daily returns."
        )
    elif volatility:
        parts.append(_volatility_sentence(volatility, evidence))
    return " ".join(parts)


def _volatility_sentence(item: dict[str, str], evidence: dict[str, Any]) -> str:
    sentence = f"Annualized volatility is {item['value']}.{_cite(item)}"
    sample = _short_volatility_clause(evidence)
    return f"{sentence} {sample}" if sample else sentence


def _short_volatility_clause(evidence: dict[str, Any]) -> str:
    item = _find(evidence, "volatility")
    count = _find(evidence, "observation_count")
    if not item or item.get("value") in {"undefined", "unavailable"}:
        return ""
    try:
        observed = int(str(count.get("value"))) if count else 0
    except (TypeError, ValueError):
        return ""
    if observed <= 0 or observed >= RECENT_WINDOW:
        return ""
    noun = "return" if observed == 1 else "returns"
    return (
        f"That uses {observed} stored daily {noun}. A short sample can make "
        "this number very large. It is not a long-run risk figure."
    )


def _return_answer(evidence: dict[str, Any]) -> str:
    item = _find(evidence, "total_return")
    value = item["value"] if item else "undefined"
    window = _find(evidence, "sample_window")
    when = f" The series runs from {window['value']}." if window else ""
    if value in {"undefined", "unavailable"}:
        return (
            "Time-weighted return is unavailable because there are not enough "
            "usable portfolio observations. Company fundamentals are not the "
            f"missing input.{when}"
        )
    return (
        f"Full-sample total return is {value}.{_cite(item)} "
        f"This is a time-weighted portfolio return, not company ROE.{when}"
    )


def _holdings_answer(evidence: dict[str, Any]) -> str:
    positions = [
        item["value"]
        for item in evidence.get("facts", [])
        if item["name"].startswith("position:")
    ]
    if not positions:
        return "No current holdings are stored."
    return "Current holdings: " + "; ".join(positions) + "."


def _absent_fact(text: str) -> str | None:
    named = (
        ("dividend", "Dividend income"),
        ("coupon", "Coupon income"),
        ("analyst target", "An analyst target"),
        ("earnings date", "An earnings date"),
        ("stock split", "A stock split"),
    )
    for needle, label in named:
        if needle in text:
            return f"{label} is not in the evidence. No other figure is substituted."
    return None


def _freshness(moves: list[dict[str, str]], evidence_date: str) -> str:
    dates = sorted({item.get("as_of", "") for item in moves if item.get("as_of")})
    dated = f" The print is as of {', '.join(dates)}." if dates else ""
    if any("Stale" in item.get("method", "") for item in moves):
        return "These day moves are stale provider prints, not a live tape." + dated
    if any("Delayed" in item.get("method", "") for item in moves):
        extra = ""
        if evidence_date and any(day != evidence_date for day in dates):
            extra = " That date is not today."
        return (
            "These day moves are delayed provider prints. "
            "Refreshing the page does not make them real-time." + dated + extra
        )
    return dated.strip()


def _quote_method(quote: LiveQuote) -> str:
    if quote.is_stale or quote.timeliness == "stale":
        return (
            "Stale provider print. This is not a live tape, and refreshing "
            "the page does not make it current."
        )
    if quote.timeliness in {"delayed", "historical"}:
        return (
            "Delayed provider print. A page refresh does not make a delayed "
            "quote real-time."
        )
    if quote.timeliness in {"realtime", "live"}:
        return "Provider print marked real-time by the quote source."
    return "Provider day change from the previous close."


def _safe_extra(body: str, direct: str, allowed: set[str]) -> str:
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", body.strip()):
        cleaned = sentence.strip()
        if not cleaned or not _sentence_ok(cleaned, allowed):
            continue
        if _about_roe(direct) and any(
            phrase in cleaned.lower() for phrase in _HISTORY_EXCUSE
        ):
            continue
        if _about_forecast(direct) and any(
            phrase in cleaned.lower() for phrase in _FORECAST_LEAK
        ):
            continue
        kept.append(cleaned)
    return " ".join(kept)


def _without_repeated_headlines(
    extra: str,
    direct: str,
    evidence: dict[str, Any],
) -> str:
    """Drop model sentences that repeat a section or paste a headline."""
    direct_folded = " ".join(direct.lower().split())
    news_ids = {
        str(item.get("id", ""))
        for item in evidence.get("facts", [])
        if str(item.get("name", "")).startswith("news:") and item.get("id")
    }
    snippets = []
    for item in evidence.get("facts", []):
        if not str(item.get("name", "")).startswith("news:"):
            continue
        folded = " ".join(str(item.get("value", "")).lower().split())
        if len(folded) >= 24:
            snippets.append(folded[:48])
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", extra.strip()):
        cleaned = sentence.strip()
        folded = " ".join(cleaned.lower().split())
        if not folded or folded in direct_folded:
            continue
        if any(f"[{item_id}]" in cleaned for item_id in news_ids):
            continue
        if any(snippet in folded for snippet in snippets):
            continue
        kept.append(cleaned)
    return " ".join(kept)


def _sentence_ok(sentence: str, allowed: set[str]) -> bool:
    visible = _CITE.sub("", sentence)
    for token in _NUMBER.findall(visible):
        if _norm_number(token) not in allowed:
            return False
    return True


def _allowed_numbers(evidence: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for item in [*evidence.get("facts", []), *evidence.get("metrics", [])]:
        _add_numbers(str(item.get("value", "")), allowed)
        _add_numbers(str(item.get("as_of", "")), allowed)
        _add_numbers(str(item.get("method", "")), allowed)
        name = str(item.get("name", ""))
        if name in _RATIO_NAMES or name.startswith(_RATIO_PREFIXES):
            _add_percent_form(str(item.get("value", "")), allowed)
    _add_numbers(str(evidence.get("evidence_date", "")), allowed)
    return allowed


def _add_numbers(text: str, allowed: set[str]) -> None:
    for token in _NUMBER.findall(text):
        allowed.add(_norm_number(token))


def _add_percent_form(value: str, allowed: set[str]) -> None:
    try:
        number = Decimal(value)
    except Exception:
        return
    percent = (number * Decimal("100")).quantize(Decimal("0.01"))
    allowed.add(_norm_number(decimal_to_json(percent)))


def _norm_number(token: str) -> str:
    raw = token.replace(",", "")
    try:
        return decimal_to_json(Decimal(raw))
    except Exception:
        return raw


def answer_is_closed(evidence: dict[str, Any]) -> bool:
    """True when the calculated answer must not gain outside sentences."""
    direct = str(evidence.get("direct_answer") or "").strip()
    return bool(direct) and _closed(direct)


def _closed(direct: str) -> bool:
    lower = direct.lower()
    return (
        "not a stored metric" in lower
        or "not in this evidence" in lower
        or "not in the evidence" in lower
        or "no forecast is given" in lower
        or "not in the stored evidence" in lower
    )


def _about_roe(direct: str) -> bool:
    lower = direct.lower()
    return "roe" in lower or "return on equity" in lower


def _about_forecast(direct: str) -> bool:
    lower = direct.lower()
    return "no forecast" in lower or "future price" in lower


def _same_words(left: str, right: str) -> bool:
    return " ".join(left.split()) == " ".join(right.split())


_FORECAST_MODAL = r"(?:will|could|might|would|gonna)"
_FORECAST_DIRECTION = (
    r"(?:rise|fall|drop|climb|outperform|crash|decline|gain|lose|"
    r"increase|decrease|higher|lower|down|up)"
)


_UNGROUNDED = re.compile(
    r"\b("
    r"tailwinds?|headwinds?|demographics?|digital transformation|"
    r"structurally|permanent decline|regulatory|antitrust|"
    r"government policy|government policies|tax change|tax changes|"
    r"single point of failure|suppliers?|commodit(?:y|ies)|"
    r"kill switch|double down|panic-sell|panic sell|"
    r"time horizon|quarterly noise|conviction|"
    r"buy more|sell the stock|should i sell|should you sell|"
    r"would i sell|would you sell|admit you were wrong"
    r")\b"
)


def _is_ungrounded(text: str) -> bool:
    """Industry structure, suppliers, and a sell rule are not stored results."""
    return _UNGROUNDED.search(text) is not None


def _limits_answer(evidence: dict[str, Any]) -> str:
    """Refuse a judgment the evidence cannot make. Do not invent one."""
    lines = [
        "Industry growth, regulatory risk, supplier overlap, and a buy or "
        "sell rule are not in the stored evidence.",
        "No tailwind, headwind, or future return is stated.",
    ]
    sectors = _sector_lines(evidence)
    if sectors:
        lines.append("Stored sector labels for the current holdings:")
        lines.extend(sectors)
        lines.append(_shared_sector_line(evidence))
    else:
        lines.append("No sector label is in this evidence.")
    policy = _policy_headlines(evidence)
    if policy:
        lines.append("Stored headlines that name a lawsuit or a policy term:")
        lines.extend(policy)
    else:
        lines.append(
            "No stored headline names a lawsuit, an antitrust case, "
            "or a policy change."
        )
    lines.append(
        "A kill switch, a decision to buy more, and your time horizon "
        "are not stored. No buy or sell instruction is given."
    )
    return "\n".join(lines)


def _sector_lines(evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in evidence.get("facts", []):
        name = str(item.get("name", ""))
        if not name.startswith("sector:"):
            continue
        ticker = name.split(":", 1)[1]
        weight = _find(evidence, f"weight:{ticker}")
        weight_text = ""
        if weight and weight.get("availability") != "unavailable":
            weight_text = f", weight {weight.get('value', '')}{_cite(weight)}"
        lines.append(
            f"{ticker} is tagged {item.get('value', '')}"
            f"{_cite(item)}{weight_text}."
        )
    return lines


def _shared_sector_line(evidence: dict[str, Any]) -> str:
    labels = {
        str(item.get("value", "")).strip()
        for item in evidence.get("facts", [])
        if str(item.get("name", "")).startswith("sector:") and item.get("value")
    }
    if len(labels) == 1:
        label = next(iter(labels))
        return (
            f"The current holdings share the sector label {label}. "
            "A shared sector label is not a shared supplier, a commodity, "
            "or a growth forecast."
        )
    return (
        "The sector labels are not the same. A sector label is not a "
        "supplier, a commodity, or a growth forecast."
    )


_POLICY_EVENT = re.compile(
    r"\b(lawsuit|lawsuits|sued|antitrust|regulat\w*|tax)\b",
    re.IGNORECASE,
)


def _policy_headlines(evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for ticker, items in _headline_groups(evidence):
        for item in items:
            headline = str(item.get("value", ""))
            if _POLICY_EVENT.search(headline):
                lines.append(f"{ticker}: {headline}{_cite(item)}")
    return lines


def _is_forecast(text: str) -> bool:
    if _mentions(text, "predict", "forecast", "tomorrow", "guarantee"):
        return True
    if any(
        phrase in text
        for phrase in (
            "next year",
            "next month",
            "next week",
            "price target",
            "going to",
        )
    ):
        return True
    # "will my portfolio go down today" is a forecast. "why did it go down
    # today" has no modal, so it stays a question about the stored print.
    return (
        re.search(
            rf"\b{_FORECAST_MODAL}\b.+\b{_FORECAST_DIRECTION}\b",
            text,
        )
        is not None
    )


def _percent_text(value: str) -> str:
    try:
        number = Decimal(value)
    except Exception:
        return value
    percent = (number * Decimal("100")).quantize(Decimal("0.01"))
    return f"{decimal_to_json(percent)}%"


def _find(evidence: dict[str, Any], name: str) -> dict[str, str] | None:
    for collection in ("metrics", "facts"):
        for item in evidence.get(collection, []):
            if item.get("name") == name:
                return item
    return None


def _cite(item: dict[str, str] | None) -> str:
    if not item or not item.get("id"):
        return ""
    return f" [{item['id']}]"


def _mentions(text: str, *phrases: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(phrase)}\b", text) is not None for phrase in phrases
    )


def _largest_weight(analytics: AnalyticsOut) -> tuple[str, str]:
    if not analytics.allocation:
        return "undefined", "undefined"
    largest = max(analytics.allocation, key=lambda line: line.weight)
    return largest.ticker, decimal_to_json(largest.weight)


def _latest_daily_return(analytics: AnalyticsOut) -> str:
    for point in reversed(analytics.series):
        if point.daily_return is not None:
            return decimal_to_json(point.daily_return)
    return "undefined"


def _compare_volatility(
    returns: list[Decimal],
    trading_days: int,
) -> dict[str, Decimal | None | str]:
    if len(returns) < RECENT_WINDOW * 2:
        return {"recent": None, "prior": None, "change": "insufficient_history"}
    prior = annualized_volatility(
        returns[-RECENT_WINDOW * 2 : -RECENT_WINDOW],
        trading_days,
    )
    recent = annualized_volatility(returns[-RECENT_WINDOW:], trading_days)
    if prior is None or recent is None:
        return {"recent": recent, "prior": prior, "change": "insufficient_history"}
    if recent > prior:
        change = "increased"
    elif recent < prior:
        change = "decreased"
    else:
        change = "unchanged"
    return {"recent": recent, "prior": prior, "change": change}


def _item(
    kind: str,
    name: str,
    value: str,
    source: str,
    *,
    seq: dict[str, int],
    label: str = "",
    method: str = "",
    as_of: str = "",
    unit: str = "",
    availability: str = "",
) -> dict[str, str]:
    if not availability:
        if value in {"undefined", "unavailable", "insufficient_history"}:
            availability = "unavailable"
        else:
            availability = "available"
    item_id = f"e{seq['n']}"
    seq["n"] += 1
    return {
        "kind": kind,
        "name": name,
        "value": value,
        "source": source,
        "id": item_id,
        "label": label or _label(name),
        "method": method,
        "as_of": as_of,
        "unit": unit,
        "availability": availability,
    }


def _resume(evidence: dict[str, Any]) -> dict[str, int]:
    highest = 0
    for item in [*evidence.get("facts", []), *evidence.get("metrics", [])]:
        raw = str(item.get("id", ""))
        if raw.startswith("e") and raw[1:].isdigit():
            highest = max(highest, int(raw[1:]))
    return {"n": highest + 1}


def _label(name: str) -> str:
    labels = {
        "metric_scope": "What these figures measure",
        "sample_window": "Daily return history",
        "allocation_history": "Past allocation",
        "total_return": "Time-weighted return",
        "volatility": "Volatility",
        "sharpe_ratio": "Sharpe ratio",
        "max_drawdown": "Maximum drawdown",
        "observation_count": "Daily return observations",
        "recent_volatility": "Recent volatility",
        "prior_volatility": "Prior volatility",
        "volatility_change": "Volatility change",
        "largest_weight_ticker": "Largest holding",
        "largest_weight": "Largest weight",
        "latest_daily_return": "Latest daily return",
        "largest_gainer": "Strongest day move",
        "largest_loser": "Weakest day move",
        "weighted_roe": "Weighted average company ROE",
        "unrealized_pl": "Unrealized profit",
        "portfolio_market_value": "Portfolio market value",
    }
    if name in labels:
        return labels[name]
    prefix, _, ticker = name.partition(":")
    named = {
        "position": f"{ticker} holding",
        "weight": f"{ticker} weight",
        "market_value": f"{ticker} market value",
        "roe": f"{ticker} return on equity",
        "pe": f"{ticker} price to earnings",
        "day_change": f"{ticker} day change",
        "average_cost": f"{ticker} average cost",
        "unrealized_pl": f"{ticker} unrealized profit",
    }
    return named.get(prefix, name.replace("_", " "))


def _num(value: Decimal | None) -> str:
    if value is None:
        return "undefined"
    return decimal_to_json(value)
