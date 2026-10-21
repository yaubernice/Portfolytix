"""Educational copy for existing Portfolytix metrics. Not user data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    slug: str
    title: str
    summary: str
    meaning: str
    why_it_matters: str
    limitations: str


TERMS: tuple[GlossaryTerm, ...] = (
    GlossaryTerm(
        slug="max-drawdown",
        title="Maximum drawdown",
        summary="The deepest fall from a peak to a later low in the return index.",
        meaning=(
            "Maximum drawdown is the largest drop from a high point to a "
            "later low point. Example: if a return index goes from 100 to 90, "
            "the drawdown is -10%. Portfolytix measures that drop on the "
            "time-weighted wealth index, which starts at 1. A deposit is not "
            "treated as a gain."
        ),
        why_it_matters=(
            "It shows how deep a decline was during the period you are "
            "looking at. A more negative number means a deeper fall from a "
            "previous peak. It describes the past sample only."
        ),
        limitations=(
            "The percentage is not a permanent loss, and it is not a forecast. "
            "Dollar portfolio value on those dates can also change because of "
            "buys and sells, so the cash change may not equal the percentage."
        ),
    ),
    GlossaryTerm(
        slug="volatility",
        title="Volatility",
        summary="How widely daily time-weighted returns varied, annualized.",
        meaning=(
            "Volatility here is the sample standard deviation of daily "
            "time-weighted returns, multiplied by the square root of 252. "
            "Example: a higher percent means the daily returns were more "
            "spread out, not that the portfolio fell."
        ),
        why_it_matters=(
            "It helps you see how bumpy the path was. Two portfolios can "
            "finish with the same return and still have very different "
            "volatility."
        ),
        limitations=(
            "It needs at least two daily returns. It treats up and down moves "
            "as variation, and it does not predict future swings. The 252-day "
            "scaling is a convention, not a promise about the next year."
        ),
    ),
    GlossaryTerm(
        slug="sharpe-ratio",
        title="Sharpe ratio",
        summary=(
            "Average daily return above a risk-free rate, divided by "
            "daily volatility."
        ),
        meaning=(
            "The Sharpe ratio is (average daily time-weighted return minus "
            "the daily risk-free rate) divided by the daily standard "
            "deviation. Portfolytix turns the annual risk-free rate into a "
            "daily figure by dividing by 252. A higher number means more "
            "return per unit of variation in this sample."
        ),
        why_it_matters=(
            "It puts return next to how uneven that return was. A large "
            "return with wild swings can score lower than a steadier one."
        ),
        limitations=(
            "It is undefined when there are fewer than two daily returns or "
            "when volatility is zero. The risk-free rate is an assumption, "
            "not a rate you earned. The ratio is not a buy or sell signal."
        ),
    ),
    GlossaryTerm(
        slug="time-weighted-return",
        title="Time-weighted return",
        summary="The portfolio's compounded daily return, with deposits removed.",
        meaning=(
            "Time-weighted return compounds each day's gain or loss after "
            "removing cash you added or withdrew. Example: buying more shares "
            "increases the portfolio's dollar value, but that deposit is not "
            "counted as investment profit. The headline figure is for the "
            "whole sample. It is not annualized."
        ),
        why_it_matters=(
            "It answers how the investments performed, separate from how "
            "much money you moved in or out."
        ),
        limitations=(
            "It is not the same as the change in your account balance. A "
            "separate annualized return may also be shown; that is a "
            "rescaling of the same sample, not a forecast."
        ),
    ),
    GlossaryTerm(
        slug="unrealized-pl",
        title="Unrealized P/L",
        summary="Current marked value minus what the open positions cost.",
        meaning=(
            "Unrealized profit or loss is the current market value of open "
            "positions minus their cost basis. Example: shares bought for "
            "100 and now marked at 110 have an unrealized gain of 10. You "
            "have not received that difference in cash."
        ),
        why_it_matters=(
            "It shows whether the positions you still hold are above or "
            "below what you paid, at the latest stored or live mark."
        ),
        limitations=(
            "It changes when the mark changes. Selling would turn it into a "
            "realized result, which this figure does not include. Missing "
            "prices leave the figure unavailable."
        ),
    ),
    GlossaryTerm(
        slug="day-pl",
        title="Day P/L",
        summary="Today's marked move, with external cash removed.",
        meaning=(
            "Day P/L is the change in value since the previous close, after "
            "removing buys and sells. Example: a position worth 100 yesterday "
            "and 103 today, with no trade, has a day P/L of 3."
        ),
        why_it_matters=(
            "It separates today's move from the gain or loss since you "
            "bought. Contributors and detractors are the positions with the "
            "largest positive and negative day P/L."
        ),
        limitations=(
            "It is one session, not a long-term result. If there is no "
            "previous mark, the day figure stays empty."
        ),
    ),
    GlossaryTerm(
        slug="pe-ratio",
        title="P/E ratio",
        summary="Price divided by earnings in the stored snapshot.",
        meaning=(
            "The price-to-earnings ratio is a company's price divided by its "
            "earnings. Example: a price of 20 and earnings of 1 is a P/E of "
            "20. Portfolytix shows the stored snapshot, not a live recalculation."
        ),
        why_it_matters=(
            "It is one way to compare how much price sits on each unit of "
            "earnings. Holdings can be looked at side by side only when each "
            "has a snapshot."
        ),
        limitations=(
            "A higher P/E is not automatically expensive, and a lower one is "
            "not automatically cheap. Earnings can be negative, outdated, or "
            "missing. The snapshot is not a recommendation."
        ),
    ),
    GlossaryTerm(
        slug="roe",
        title="ROE",
        summary="Stored return on equity: earnings compared with equity.",
        meaning=(
            "Return on equity is earnings compared with shareholders' equity. "
            "Example: 0.15 in the database means 15%. Portfolytix shows the "
            "stored snapshot for a security."
        ),
        why_it_matters=(
            "It is one profitability figure already used by screening. It "
            "describes the company snapshot, not your personal gain."
        ),
        limitations=(
            "A high ROE can come from low equity as well as from high "
            "earnings. The snapshot can be missing, and it does not predict "
            "the share price."
        ),
    ),
)

BY_SLUG = {term.slug: term for term in TERMS}

# Standard formulas, written to match Portfolytix's calculations.
FORMULAS: dict[str, str] = {
    "max-drawdown": "MDD = min(Wₜ / running peak of W − 1)",
    "volatility": "σ annual = sample stdev(daily returns) × √252",
    "sharpe-ratio": "Sharpe = (average daily return − r_f / 252) / daily stdev",
    "time-weighted-return": (
        "rₜ = (Vₜ − Vₜ₋₁ − cash flowₜ) / Vₜ₋₁; "
        "total = Π(1 + rₜ) − 1"
    ),
    "unrealized-pl": "Unrealized P/L = current market value − cost basis",
    "day-pl": "Day P/L = today's value − previous value − today's cash flow",
    "pe-ratio": "P/E = price / earnings",
    "roe": "ROE = net income / shareholders' equity",
}

@dataclass(frozen=True, slots=True)
class TermCard:
    what: str
    example: str
    watch: str


# Short beginner lines. Portfolio numbers are added separately.
CARDS: dict[str, TermCard] = {
    "max-drawdown": TermCard(
        what="The biggest fall from a high point to a later low.",
        example="Up from 100 to 110, then down to 99, is a −10% drawdown.",
        watch="A past drop. Not money gone forever, and not a forecast.",
    ),
    "volatility": TermCard(
        what="How much the daily results jumped around, scaled to a year.",
        example="Two portfolios can both gain 10%. The jumpy one is more volatile.",
        watch="Needs at least two daily returns. Not a forecast.",
    ),
    "sharpe-ratio": TermCard(
        what="Return above a cash rate, for each bit of bumpiness.",
        example="A steady gain can score higher than a wild one.",
        watch="Needs two daily returns. Not a buy or sell signal.",
    ),
    "time-weighted-return": TermCard(
        what="How the investments did, ignoring money you added or withdrew.",
        example="From 100 to 110 with no deposit is a 10% gain.",
        watch="This is the whole period, not a yearly forecast.",
    ),
    "unrealized-pl": TermCard(
        what="What you would gain or lose if you sold at today's price.",
        example="Bought at 100, now worth 110: a gain of 10, still unsold.",
        watch="It changes when the price changes. It is not cash yet.",
    ),
    "day-pl": TermCard(
        what="How much value changed today, ignoring buys and sells.",
        example="Worth 100 yesterday and 103 today, with no trade: a gain of 3.",
        watch="One day only. Not the gain since you bought.",
    ),
    "pe-ratio": TermCard(
        what="Price divided by the company's earnings.",
        example="A price of 20 and earnings of 1 is a P/E of 20.",
        watch="Higher is not automatically expensive.",
    ),
    "roe": TermCard(
        what="Earnings compared with shareholder money in the company.",
        example="0.15 in the data means 15%.",
        watch="This is about the company, not your personal gain.",
    ),
}

ALIASES: dict[str, str] = {
    "max drawdown": "max-drawdown",
    "maximum drawdown": "max-drawdown",
    "drawdown": "max-drawdown",
    "volatility": "volatility",
    "sharpe": "sharpe-ratio",
    "sharpe ratio": "sharpe-ratio",
    "total return": "time-weighted-return",
    "time-weighted return": "time-weighted-return",
    "time weighted return": "time-weighted-return",
    "cumulative return": "time-weighted-return",
    "twr": "time-weighted-return",
    "unrealized p/l": "unrealized-pl",
    "unrealized p&l": "unrealized-pl",
    "unrealized pnl": "unrealized-pl",
    "unrealized profit": "unrealized-pl",
    "day change": "day-pl",
    "day p/l": "day-pl",
    "day p&l": "day-pl",
    "daily p/l": "day-pl",
    "p/e": "pe-ratio",
    "p/e ratio": "pe-ratio",
    "pe": "pe-ratio",
    "pe ratio": "pe-ratio",
    "roe": "roe",
    "return on equity": "roe",
}


def match_term(text: str) -> GlossaryTerm | None:
    """Match a clicked label. Unknown phrases are not another metric."""
    raw = " ".join(text.lower().split())
    slug = ALIASES.get(raw)
    if slug is not None:
        return BY_SLUG.get(slug)
    compact = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return BY_SLUG.get(compact)
