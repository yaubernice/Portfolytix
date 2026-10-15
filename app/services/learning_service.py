"""Learning pages. Education is static. Figures come from existing services."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.local import LocalAssistant
from app.ai.provider import AssistantModel
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.db.models.fundamental import Fundamental
from app.db.models.security import Security
from app.learning.glossary import BY_SLUG, CARDS, FORMULAS, TERMS, match_term
from app.repositories.security_repository import SecurityRepository
from app.schemas.analytics import AnalyticsOut, SeriesPoint
from app.schemas.learning import (
    ExplainOut,
    LearnCatalog,
    LearnFact,
    LearnObservation,
    LearnPage,
    LearnTermSummary,
)
from app.schemas.position import PositionOut, PositionsResponse
from app.services.analytics_service import AnalyticsService
from app.services.position_service import PositionService

DISCLAIMER = (
    "This page explains a metric. It is not investment advice and does not "
    "predict future performance."
)
_CHOOSE = (
    "Choose a portfolio to see your own figures. The sections above are "
    "general and do not use your data."
)
_PERFORMANCE = frozenset(
    {"max-drawdown", "volatility", "sharpe-ratio", "time-weighted-return"}
)


class LearningService:
    def __init__(
        self,
        session: Session,
        analytics: AnalyticsService,
        positions: PositionService,
        model: AssistantModel,
    ) -> None:
        self.session = session
        self.analytics = analytics
        self.positions = positions
        self.model = model
        self.securities = SecurityRepository(session)

    def catalog(self) -> LearnCatalog:
        return LearnCatalog(
            terms=[
                LearnTermSummary(
                    slug=term.slug, title=term.title, summary=term.summary
                )
                for term in TERMS
            ]
        )

    def page(
        self,
        slug: str,
        *,
        portfolio_id: UUID | None,
        ticker: str | None,
    ) -> LearnPage:
        term = BY_SLUG.get(slug)
        if term is None:
            raise NotFoundError(f"Learning term {slug} not found")
        symbol = ticker.strip().upper() if ticker else None
        positions, analytics, blocked = self._context(portfolio_id, slug)
        observation = self._observation(slug, positions, analytics, blocked, symbol)
        card = _card(term.slug, observation)
        return LearnPage(
            slug=term.slug,
            title=term.title,
            formula=card["formula"],
            what=card["what"],
            example=card["example"],
            yours=card["yours"],
            watch=card["watch"],
            explanation=_joined(card),
            meaning=term.meaning,
            why_it_matters=term.why_it_matters,
            limitations=term.limitations,
            portfolio_id=portfolio_id,
            ticker=symbol,
            observation=observation,
            disclaimer=DISCLAIMER,
        )

    def explain(
        self,
        text: str,
        *,
        portfolio_id: UUID | None,
        ticker: str | None,
    ) -> ExplainOut:
        cleaned = " ".join(text.split())
        if not cleaned or len(cleaned) > 80:
            raise AppError("Enter a word or short phrase to explain")
        term = match_term(cleaned)
        if term is not None:
            page = self.page(term.slug, portfolio_id=portfolio_id, ticker=ticker)
            return ExplainOut(
                title=page.title,
                formula=page.formula,
                what=page.what,
                example=page.example,
                yours=page.yours,
                watch=page.watch,
                explanation=page.explanation,
                source="glossary",
                disclaimer=page.disclaimer,
            )
        symbol = ticker.strip().upper() if ticker else None
        evidence = self._model_evidence(portfolio_id, symbol)
        drafted, source = self._draft(cleaned, evidence)
        return ExplainOut(
            title=cleaned,
            formula=drafted["formula"],
            what=drafted["what"],
            example=drafted["example"],
            yours=drafted["yours"],
            watch=drafted["watch"],
            explanation=_joined(drafted),
            source=source,
            disclaimer=DISCLAIMER,
        )

    def _draft(self, text: str, evidence: dict) -> tuple[dict, str]:
        try:
            drafted = self.model.explain_term(text, evidence)
            source = (
                "model" if self.model.interpretation_source == "llm" else "template"
            )
        except AppError:
            drafted = LocalAssistant().explain_term(text, evidence)
            source = "template"
        what = drafted.get("what", "")
        if not isinstance(what, str) or not what.strip():
            drafted = LocalAssistant().explain_term(text, evidence)
            source = "template"
        formula = drafted.get("formula", "")
        return {
            "what": str(drafted.get("what", "")).strip(),
            "example": str(drafted.get("example", "")).strip(),
            "yours": str(drafted.get("yours", "")).strip(),
            "watch": str(drafted.get("watch", "")).strip(),
            "formula": formula.strip() if isinstance(formula, str) else "",
        }, source

    def _model_evidence(
        self, portfolio_id: UUID | None, ticker: str | None
    ) -> dict:
        if portfolio_id is None:
            return {"facts": [], "note": _CHOOSE}
        positions, analytics, blocked = self._context(portfolio_id, "max-drawdown")
        facts: list[dict[str, str]] = []
        if analytics is None:
            note = blocked or "Portfolio analytics are unavailable."
        else:
            note = ""
            for slug in (
                "time-weighted-return",
                "volatility",
                "sharpe-ratio",
                "max-drawdown",
            ):
                observation = _performance(slug, analytics)
                facts.append(
                    {"label": slug, "value": _short_yours(slug, observation)}
                )
        if positions is not None:
            for slug in ("unrealized-pl", "day-pl"):
                observation = _profit(slug, positions)
                facts.append(
                    {"label": slug, "value": _short_yours(slug, observation)}
                )
            if ticker:
                observation = self._fundamental("pe-ratio", positions, ticker)
                facts.append(
                    {"label": ticker, "value": _short_yours("pe-ratio", observation)}
                )
        return {"facts": facts, "note": note}

    def _context(
        self, portfolio_id: UUID | None, slug: str
    ) -> tuple[PositionsResponse | None, AnalyticsOut | None, str | None]:
        if portfolio_id is None:
            return None, None, None
        positions = self.positions.list_positions(portfolio_id)
        if slug not in _PERFORMANCE:
            return positions, None, None
        try:
            return positions, self.analytics.get_analytics(portfolio_id), None
        except ConflictError as exc:
            return positions, None, exc.message

    def _observation(
        self,
        slug: str,
        positions: PositionsResponse | None,
        analytics: AnalyticsOut | None,
        blocked: str | None,
        ticker: str | None,
    ) -> LearnObservation:
        if slug in _PERFORMANCE:
            if positions is None:
                return _missing(_CHOOSE)
            if blocked or analytics is None:
                reason = blocked or "Portfolio analytics are unavailable."
                return _missing(f"{reason} The general explanation still applies.")
            return _performance(slug, analytics)
        if slug in {"unrealized-pl", "day-pl"}:
            if positions is None:
                return _missing(_CHOOSE)
            return _profit(slug, positions)
        return self._fundamental(slug, positions, ticker)

    def _fundamental(
        self,
        slug: str,
        positions: PositionsResponse | None,
        ticker: str | None,
    ) -> LearnObservation:
        if ticker:
            return self._one_security(slug, positions, ticker)
        if positions is None:
            return _missing(_CHOOSE)
        rows = [row for row in positions.positions if row.quantity > 0]
        if not rows:
            return _missing("This portfolio has no open positions to look up.")
        snapshots = self._snapshots([row.security_id for row in rows])
        by_id = {security.id: fundamental for security, fundamental in snapshots}
        label = "P/E" if slug == "pe-ratio" else "ROE"
        facts: list[LearnFact] = []
        for row in rows:
            fundamental = by_id.get(row.security_id)
            if fundamental is None:
                facts.append(
                    LearnFact(label=row.ticker, value=f"No stored {label} snapshot")
                )
                continue
            facts.append(
                LearnFact(
                    label=f"{row.ticker} as of {fundamental.as_of.isoformat()}",
                    value=_snapshot_value(slug, fundamental),
                )
            )
        if not snapshots:
            return _missing(
                f"No open position has a stored {label} snapshot, so this "
                "cannot be applied to the current holdings."
            )
        names = ", ".join(
            f"{security.ticker} {_snapshot_value(slug, fundamental)}"
            for security, fundamental in snapshots
        )
        return LearnObservation(
            available=True,
            summary=(
                f"Stored {label} snapshots for open positions: {names}. "
                "These describe the companies, not your personal gain, and "
                "they are not a recommendation."
            ),
            facts=facts,
        )

    def _one_security(
        self,
        slug: str,
        positions: PositionsResponse | None,
        ticker: str,
    ) -> LearnObservation:
        security = self.securities.get_by_ticker(ticker)
        label = "P/E" if slug == "pe-ratio" else "ROE"
        if security is None:
            return _missing(f"No stored security matches {ticker}.")
        fundamental = self.session.scalar(
            select(Fundamental).where(Fundamental.security_id == security.id)
        )
        held = _held(positions, security.id)
        if fundamental is None:
            return _missing(_no_snapshot(security.ticker, label, positions, held))
        shown = _snapshot_value(slug, fundamental)
        holding = _holding_sentence(security.ticker, positions, held)
        return LearnObservation(
            available=True,
            summary=(
                f"The stored {label} for {security.ticker} is {shown} as of "
                f"{fundamental.as_of.isoformat()}. {holding} This is a company "
                "snapshot, not your personal gain, and not a recommendation."
            ),
            facts=[
                LearnFact(label=label, value=shown),
                LearnFact(label="As of", value=fundamental.as_of.isoformat()),
                LearnFact(
                    label="Open position in the selected portfolio",
                    value=_held_label(positions, held),
                ),
            ],
        )

    def _snapshots(
        self, security_ids: list[UUID]
    ) -> list[tuple[Security, Fundamental]]:
        rows = self.session.execute(
            select(Security, Fundamental)
            .join(Fundamental, Fundamental.security_id == Security.id)
            .where(Security.id.in_(security_ids))
        ).all()
        return [(security, fundamental) for security, fundamental in rows]


def _performance(slug: str, analytics: AnalyticsOut) -> LearnObservation:
    if slug == "max-drawdown":
        return _drawdown(analytics)
    if slug == "volatility":
        return _volatility(analytics)
    if slug == "sharpe-ratio":
        return _sharpe(analytics)
    return _twr(analytics)


def _drawdown(analytics: AnalyticsOut) -> LearnObservation:
    value = analytics.max_drawdown
    count = analytics.observation_count
    if value is None or count == 0:
        noun = "return" if count == 1 else "returns"
        stored = ""
        if value is not None:
            stored = (
                f" The stored figure is {_percent(value)} because an empty "
                "return path has no decline to measure."
            )
        return _missing(
            "Maximum drawdown needs at least one daily time-weighted return "
            "so a peak and a later trough can be compared. This sample has "
            f"{count} daily {noun}.{stored} This is not a forecast."
        )
    sample = _sample_facts(analytics)
    if value == 0:
        return LearnObservation(
            available=True,
            summary=(
                "In this sample the time-weighted wealth index did not fall "
                "below a prior peak, so the maximum drawdown is 0.0%. That "
                "describes this period only. It is not a forecast."
            ),
            facts=[LearnFact(label="Maximum drawdown", value="0.0%"), *sample],
        )
    peak, trough = _peak_and_trough(analytics.series)
    facts = [LearnFact(label="Maximum drawdown", value=_percent(value))]
    if peak is None or trough is None:
        facts.extend(sample)
        return LearnObservation(
            available=True,
            summary=(
                f"The maximum drawdown in this sample is {_percent(value)}. "
                "The stored series does not identify a separate peak and "
                "trough. This is not a permanent loss and not a forecast."
            ),
            facts=facts,
        )
    facts.extend(
        [
            LearnFact(label="Peak date", value=peak.date.isoformat()),
            LearnFact(
                label="Portfolio value on the peak date",
                value=_money(peak.value),
            ),
            LearnFact(label="Trough date", value=trough.date.isoformat()),
            LearnFact(
                label="Portfolio value on the trough date",
                value=_money(trough.value),
            ),
            *sample,
        ]
    )
    return LearnObservation(
        available=True,
        summary=(
            f"The time-weighted wealth index fell {_percent(value)} from a "
            f"peak on {peak.date.isoformat()} to a trough on "
            f"{trough.date.isoformat()}. Portfolio value was "
            f"{_money(peak.value)} on the peak date and "
            f"{_money(trough.value)} on the trough date. Those dollar values "
            "can differ from the percentage because buys and sells are "
            "removed from the return index. This is not a permanent loss "
            "and not a forecast."
        ),
        facts=facts,
    )


def _peak_and_trough(
    series: list[SeriesPoint],
) -> tuple[SeriesPoint | None, SeriesPoint | None]:
    wealth = Decimal(1)
    peak_wealth = Decimal(1)
    peak_index = 0
    worst = Decimal(0)
    trough_index: int | None = None
    peak_at_trough = 0
    for index, point in enumerate(series):
        if point.cumulative_return is not None:
            wealth = Decimal(1) + point.cumulative_return
        if wealth >= peak_wealth:
            peak_wealth = wealth
            peak_index = index
        if point.drawdown < worst:
            worst = point.drawdown
            trough_index = index
            peak_at_trough = peak_index
    if trough_index is None:
        return None, None
    return series[peak_at_trough], series[trough_index]


def _volatility(analytics: AnalyticsOut) -> LearnObservation:
    value = analytics.volatility
    if value is None:
        return _missing(
            "Volatility needs at least two daily time-weighted returns. "
            f"This sample has {analytics.observation_count}."
        )
    days = analytics.assumptions.trading_days_per_year
    return LearnObservation(
        available=True,
        summary=(
            f"Annualized volatility for this sample is {_percent(value)}. "
            "It is the sample standard deviation of daily time-weighted "
            f"returns, multiplied by the square root of {days}. A higher "
            "number means the daily returns were more spread out. It is "
            "not a forecast."
        ),
        facts=[
            LearnFact(label="Annualized volatility", value=_percent(value)),
            LearnFact(label="Trading-day convention", value=str(days)),
            *_sample_facts(analytics),
        ],
    )


def _sharpe(analytics: AnalyticsOut) -> LearnObservation:
    value = analytics.sharpe_ratio
    rate = analytics.assumptions.risk_free_rate_annual
    if value is None:
        if analytics.volatility is None:
            reason = (
                "The Sharpe ratio needs at least two daily time-weighted "
                f"returns. This sample has {analytics.observation_count}."
            )
        elif analytics.volatility == 0:
            reason = (
                "The Sharpe ratio is undefined because daily volatility is "
                "zero, so there is nothing to divide by."
            )
        else:
            reason = "The Sharpe ratio is undefined for this sample."
        return _missing(reason)
    shown = _number(value)
    return LearnObservation(
        available=True,
        summary=(
            f"The Sharpe ratio for this sample is {shown}. It compares the "
            "average daily time-weighted return with a "
            f"{_percent(rate)} annual risk-free assumption, then divides by "
            "daily volatility. A higher number means more return per unit of "
            "variation in this sample. It is not a buy or sell signal."
        ),
        facts=[
            LearnFact(label="Sharpe ratio", value=shown),
            LearnFact(label="Risk-free rate assumption", value=_percent(rate)),
            *_sample_facts(analytics),
        ],
    )


def _twr(analytics: AnalyticsOut) -> LearnObservation:
    value = analytics.total_return
    if value is None or analytics.observation_count == 0:
        stored = ""
        if value is not None and analytics.observation_count == 0:
            stored = (
                f" The stored figure is {_percent(value)} because there is "
                "no daily return to compound."
            )
        return _missing(
            "Time-weighted return needs at least one daily return. This "
            f"sample has {analytics.observation_count}.{stored}"
        )
    facts = [
        LearnFact(label="Time-weighted return", value=_percent(value)),
        *_sample_facts(analytics),
    ]
    summary = (
        f"The time-weighted return from {analytics.start_date} to "
        f"{analytics.end_date} is {_percent(value)}. Deposits and "
        "withdrawals are not counted as investment profit. This figure is "
        "for the whole sample and is not annualized."
    )
    if analytics.annualized_return is not None:
        facts.append(
            LearnFact(
                label="Annualized return, separate from the period figure",
                value=_percent(analytics.annualized_return),
            )
        )
    return LearnObservation(available=True, summary=summary, facts=facts)


def _profit(slug: str, positions: PositionsResponse) -> LearnObservation:
    open_rows = [row for row in positions.positions if row.quantity > 0]
    if not open_rows:
        return _missing(
            "This portfolio has no open positions, so this figure is empty."
        )
    if slug == "unrealized-pl":
        return _unrealized(positions, open_rows)
    total = positions.day_pl
    if total is None:
        return _missing(
            "Day P/L cannot be calculated because a previous or current mark "
            "is missing."
        )
    return LearnObservation(
        available=True,
        summary=(
            f"Day P/L is {_money(total)} across open positions. It is the "
            "latest session's move after removing buys and sells, not the "
            "gain or loss since purchase."
        ),
        facts=[
            LearnFact(label="Day P/L", value=_money(total)),
            *_holding_facts(open_rows, "day_pl", "day P/L"),
        ],
    )


def _unrealized(
    positions: PositionsResponse, open_rows: list[PositionOut]
) -> LearnObservation:
    total = positions.unrealized_pl
    if total is None:
        return _missing(
            "Unrealized P/L cannot be calculated because a current price is "
            "missing for an open position."
        )
    return LearnObservation(
        available=True,
        summary=(
            f"Unrealized P/L is {_money(total)}. That is the latest marked "
            "value of open positions minus their cost basis. It changes if "
            "the marks change, and it is not cash until a sale."
        ),
        facts=[
            LearnFact(label="Unrealized P/L", value=_money(total)),
            LearnFact(
                label="Cost basis", value=_money_or_blank(positions.cost_basis)
            ),
            LearnFact(
                label="Market value",
                value=_money_or_blank(positions.market_value),
            ),
            *_holding_facts(open_rows, "unrealized_pl", "unrealized P/L"),
        ],
    )


def _holding_facts(
    rows: list[PositionOut], field: str, caption: str
) -> list[LearnFact]:
    ranked = sorted(
        rows,
        key=lambda row: abs(getattr(row, field) or Decimal(0)),
        reverse=True,
    )
    facts: list[LearnFact] = []
    for row in ranked[:8]:
        amount = getattr(row, field)
        if amount is None:
            continue
        facts.append(LearnFact(label=f"{row.ticker} {caption}", value=_money(amount)))
    return facts


def _no_snapshot(
    ticker: str,
    label: str,
    positions: PositionsResponse | None,
    held: bool,
) -> str:
    sentence = (
        f"No fundamental snapshot is stored for {ticker}, so its {label} "
        "cannot be shown."
    )
    if positions is None:
        return sentence
    if held:
        return f"{sentence} It is an open position."
    return f"{sentence} It is not an open position in the selected portfolio."


def _holding_sentence(
    ticker: str, positions: PositionsResponse | None, held: bool
) -> str:
    if positions is None:
        return "No portfolio is selected, so holding status is not shown."
    if held:
        return f"{ticker} is an open position in the selected portfolio."
    return f"{ticker} is not an open position in the selected portfolio."


def _held_label(positions: PositionsResponse | None, held: bool) -> str:
    if positions is None:
        return "Not selected"
    return "Yes" if held else "No"


def _held(positions: PositionsResponse | None, security_id: UUID) -> bool:
    if positions is None:
        return False
    return any(
        row.security_id == security_id and row.quantity > 0
        for row in positions.positions
    )


def _snapshot_value(slug: str, fundamental: Fundamental) -> str:
    if slug == "pe-ratio":
        return _number(fundamental.pe_ratio)
    return _percent(fundamental.roe)


def _sample_facts(analytics: AnalyticsOut) -> list[LearnFact]:
    return [
        LearnFact(
            label="Sample",
            value=f"{analytics.start_date} to {analytics.end_date}",
        ),
        LearnFact(
            label="Daily return observations",
            value=str(analytics.observation_count),
        ),
    ]


def _card(slug: str, observation: LearnObservation) -> dict[str, str]:
    card = CARDS[slug]
    return {
        "what": card.what,
        "example": card.example,
        "yours": _short_yours(slug, observation),
        "watch": card.watch,
        "formula": FORMULAS.get(slug, ""),
    }


def _joined(parts: dict[str, str]) -> str:
    return " ".join(
        part
        for part in (
            parts.get("what", ""),
            parts.get("example", ""),
            parts.get("yours", ""),
            parts.get("watch", ""),
        )
        if part
    )


def _short_yours(slug: str, observation: LearnObservation) -> str:
    facts = {fact.label: fact.value for fact in observation.facts}
    if not observation.available:
        return _unavailable_line(observation)
    if slug == "max-drawdown":
        value = facts.get("Maximum drawdown", "")
        peak = facts.get("Peak date")
        trough = facts.get("Trough date")
        if peak and trough:
            return f"Yours is {value}. Peak {peak}, trough {trough}."
        if value == "0.0%":
            return "Yours is 0.0%. It did not fall below an earlier peak."
        return f"Yours is {value}."
    if slug == "volatility":
        return f"Yours is {facts.get('Annualized volatility', '')} a year."
    if slug == "sharpe-ratio":
        rate = facts.get("Risk-free rate assumption", "")
        return f"Yours is {facts.get('Sharpe ratio', '')}. Cash-rate assumption {rate}."
    if slug == "time-weighted-return":
        sample = facts.get("Sample", "this sample")
        value = facts.get("Time-weighted return", "")
        return f"Yours is {value} for {sample}."
    if slug == "unrealized-pl":
        return f"Yours is {facts.get('Unrealized P/L', '')}."
    if slug == "day-pl":
        return f"Yours is {facts.get('Day P/L', '')} today."
    if slug in {"pe-ratio", "roe"} and observation.facts:
        first = observation.facts[0]
        return f"{first.label}: {first.value}."
    if observation.facts:
        first = observation.facts[0]
        return f"{first.label}: {first.value}."
    return observation.summary.split(". ")[0].rstrip(".") + "."


def _unavailable_line(observation: LearnObservation) -> str:
    text = observation.unavailable_reason or "Not available for this portfolio yet."
    sentence = text.split(". ")[0].strip().rstrip(".")
    if len(sentence) > 120:
        sentence = sentence[:117].rsplit(" ", 1)[0]
    return sentence + "."


def _missing(reason: str) -> LearnObservation:
    return LearnObservation(
        available=False, summary=reason, unavailable_reason=reason
    )


def _percent(value: Decimal) -> str:
    points = (value * Decimal(100)).quantize(Decimal("0.1"))
    return f"{points}%"


def _number(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    return f"{sign}${format(abs(quantized), ',.2f')}"


def _money_or_blank(value: Decimal | None) -> str:
    if value is None:
        return "Unavailable"
    return _money(value)
