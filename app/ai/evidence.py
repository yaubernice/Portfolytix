from __future__ import annotations

from decimal import Decimal

from app.quotes.models import LiveQuote
from app.schemas.analytics import AnalyticsOut
from app.schemas.common import decimal_to_json
from app.services.analytics import annualized_volatility

# About one trading month. Two windows are required before a comparison.
RECENT_WINDOW = 21


def build_evidence(analytics: AnalyticsOut) -> dict[str, list[dict[str, str]]]:
    """Facts and metrics only. This dict is the only context a model may see."""
    facts: list[dict[str, str]] = [
        _item(
            "fact",
            "sample_window",
            f"{analytics.start_date} to {analytics.end_date}",
            "database",
        ),
        _item(
            "fact",
            "allocation_history",
            "not stored; current weights only",
            "database",
        ),
    ]
    weights: list[dict[str, str]] = []
    for line in analytics.allocation:
        facts.append(
            _item(
                "fact",
                f"position:{line.ticker}",
                (
                    f"{line.ticker} quantity {decimal_to_json(line.quantity)} "
                    f"latest price {decimal_to_json(line.price)}"
                ),
                "database",
            )
        )
        weights.append(
            _item(
                "metric",
                f"weight:{line.ticker}",
                decimal_to_json(line.weight),
                "calculation",
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
    metrics = [
        _item("metric", "total_return", _num(analytics.total_return), "calculation"),
        _item("metric", "volatility", _num(analytics.volatility), "calculation"),
        _item(
            "metric",
            "sharpe_ratio",
            _num(analytics.sharpe_ratio),
            "calculation",
        ),
        _item(
            "metric",
            "max_drawdown",
            _num(analytics.max_drawdown),
            "calculation",
        ),
        _item(
            "metric",
            "observation_count",
            str(analytics.observation_count),
            "calculation",
        ),
        _item(
            "metric",
            "recent_volatility",
            _num(comparison["recent"]),
            "calculation",
        ),
        _item(
            "metric",
            "prior_volatility",
            _num(comparison["prior"]),
            "calculation",
        ),
        _item(
            "metric",
            "volatility_change",
            str(comparison["change"]),
            "calculation",
        ),
        _item(
            "metric",
            "largest_weight_ticker",
            largest[0],
            "calculation",
        ),
        _item("metric", "largest_weight", largest[1], "calculation"),
        _item(
            "metric",
            "latest_daily_return",
            _latest_daily_return(analytics),
            "calculation",
        ),
    ]
    return {"facts": facts, "metrics": weights + metrics}


def attach_live_moves(
    evidence: dict[str, list[dict[str, str]]],
    analytics: AnalyticsOut,
    quotes: list[LiveQuote],
) -> dict[str, list[dict[str, str]]]:
    """Add day-change metrics from live quotes. Missing quotes add nothing."""
    by_ticker = {quote.ticker: quote for quote in quotes}
    moves: list[tuple[str, Decimal]] = []
    for line in analytics.allocation:
        quote = by_ticker.get(line.ticker)
        if quote is None or quote.change_percent is None:
            continue
        moves.append((line.ticker, quote.change_percent))
        evidence["metrics"].append(
            _item(
                "metric",
                f"day_change:{line.ticker}",
                decimal_to_json(quote.change_percent),
                "calculation",
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
        )
    )
    evidence["metrics"].append(
        _item(
            "metric",
            "largest_loser",
            f"{loser[0]} {decimal_to_json(loser[1])}",
            "calculation",
        )
    )
    return evidence


def render_interpretation(
    evidence: dict[str, list[dict[str, str]]],
) -> str:  # template wording
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
    volatility_text = (
        "undefined." if volatility == "undefined" else f"{volatility}."
    )
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
        "Historical allocation is not stored, so an allocation change "
        "is not measured.",
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
) -> dict[str, str]:  # such that evidence has the same structure
    return {"kind": kind, "name": name, "value": value, "source": source}


def _num(value: Decimal | None) -> str: #convert decimal to JSON string
    if value is None:
        return "undefined"
    return decimal_to_json(value)
