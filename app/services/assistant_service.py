from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.ai.evidence import (
    CompanySnapshot,
    HoldingCost,
    answer_is_closed,
    attach_headlines,
    attach_live_moves,
    build_evidence,
    direct_answer,
)
from app.ai.local import LocalAssistant
from app.ai.parsing import drop_unmentioned, parse_screen_text
from app.ai.provider import AssistantModel
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.metrics import get_metrics
from app.db.models import Fundamental, Security
from app.quotes.store import QuoteStore
from app.schemas.analytics import AnalyticsOut
from app.schemas.assistant import AssistantAnswer, EvidenceItem
from app.schemas.common import decimal_to_json
from app.schemas.screening import (
    ScreenRequest,
    ScreenResponse,
    ScreenSort,
    SortDirection,
)
from app.services.analytics_service import AnalyticsService
from app.services.positions import CostFill, average_cost_positions
from app.services.screening_service import ScreeningService

_DISCLAIMER = (
    "Not investment advice. Facts come from stored transactions and prices. "
    "Metrics are Portfolytix calculations. The interpretation only restates "
    "those values."
)


@dataclass(frozen=True, slots=True)
class AssistantEvidence:
    portfolio_id: UUID
    evidence: dict


class AssistantService:
    """Load portfolio evidence first, then ask the model to phrase it."""

    def __init__(
        self,
        analytics: AnalyticsService,
        model: AssistantModel,
        quotes: QuoteStore | None = None,
    ) -> None:
        self.analytics = analytics
        self.model = model
        self.quotes = quotes

    def ask(self, portfolio_id: UUID, question: str) -> AssistantAnswer:
        prepared = self.prepare(portfolio_id)
        _detach_chart(prepared.evidence)
        _remember_direct(prepared.evidence, question)
        if answer_is_closed(prepared.evidence):
            return self._answer(
                prepared,
                question,
                str(prepared.evidence["direct_answer"]),
                "template",
            )
        started = time.monotonic()
        source = self.model.interpretation_source
        try:
            interpretation = self.model.interpret(question, prepared.evidence)
        except Exception:
            get_metrics().increment("ai.errors")
            if not self._can_fallback():
                raise
            fallback = LocalAssistant()
            interpretation = fallback.interpret(question, prepared.evidence)
            source = fallback.interpretation_source
        else:
            source = _reported_source(source, interpretation, prepared.evidence)
        finally:
            get_metrics().observe("ai.latency", time.monotonic() - started)
        return self._answer(prepared, question, interpretation, source)

    def prepare(self, portfolio_id: UUID) -> AssistantEvidence:
        # Ownership and calculations happen here. The model is not involved.
        analytics = self.analytics.get_analytics(portfolio_id)
        evidence = build_evidence(
            analytics,
            companies=self._company_snapshots(analytics),
            costs=self._holding_costs(analytics),
            today=date.today(),
        )
        if self.quotes is not None:
            evidence = attach_live_moves(
                evidence,
                analytics,
                self.quotes.snapshot(),
            )
            evidence = attach_headlines(
                evidence,
                _stored_headlines(self.quotes, analytics),
            )
        evidence["chart"] = [
            {
                "date": point.date.isoformat(),
                "value": decimal_to_json(point.value),
            }
            for point in analytics.series[-90:]
        ]
        return AssistantEvidence(portfolio_id=portfolio_id, evidence=evidence)

    def stream(
        self,
        prepared: AssistantEvidence,
        question: str,
    ) -> Iterator[str]:
        _remember_direct(prepared.evidence, question)
        if answer_is_closed(prepared.evidence):
            source = "template"
            evidence_event = {
                "portfolio_id": str(prepared.portfolio_id),
                "question": question,
                "facts": prepared.evidence["facts"],
                "metrics": prepared.evidence["metrics"],
                "chart": _detach_chart(prepared.evidence),
                "interpretation_source": source,
                "disclaimer": _DISCLAIMER,
            }
            yield _sse("evidence", evidence_event)
            yield _sse("text", {"delta": str(prepared.evidence["direct_answer"])})
            yield _sse("done", {"done": True, "interpretation_source": source})
            return
        source = self.model.interpretation_source
        evidence_event = {
            "portfolio_id": str(prepared.portfolio_id),
            "question": question,
            "facts": prepared.evidence["facts"],
            "metrics": prepared.evidence["metrics"],
            "chart": _detach_chart(prepared.evidence),
            "interpretation_source": source,
            "disclaimer": _DISCLAIMER,
        }
        yield _sse("evidence", evidence_event)
        started = time.monotonic()
        try:
            parts: list[str] = []
            for chunk in self.model.stream_interpret(question, prepared.evidence):
                if chunk:
                    parts.append(chunk)
                    yield _sse("text", {"delta": chunk})
            source = _reported_source(source, "".join(parts), prepared.evidence)
            yield _sse(
                "done",
                {"done": True, "interpretation_source": source},
            )
        except Exception:
            get_metrics().increment("ai.errors")
            if self._can_fallback():
                fallback = LocalAssistant()
                evidence_event["interpretation_source"] = fallback.interpretation_source
                yield _sse("evidence", evidence_event)
                for chunk in fallback.stream_interpret(question, prepared.evidence):
                    yield _sse("text", {"delta": chunk})
                yield _sse(
                    "done",
                    {
                        "done": True,
                        "fallback": True,
                        "interpretation_source": fallback.interpretation_source,
                    },
                )
            else:
                yield _sse("error", {"message": "Assistant interpretation failed"})
        finally:
            get_metrics().observe("ai.latency", time.monotonic() - started)

    def _company_snapshots(
        self,
        analytics: AnalyticsOut,
    ) -> list[CompanySnapshot] | None:
        # Unit-test doubles have no database session. Leave company ratios out
        # rather than inventing them. A real session loads only this portfolio.
        portfolios = getattr(self.analytics, "portfolios", None)
        session = getattr(portfolios, "session", None)
        if session is None:
            return None
        ids = [line.security_id for line in analytics.allocation]
        rows: list[Fundamental] = []
        if ids:
            rows = list(
                session.scalars(
                    select(Fundamental).where(Fundamental.security_id.in_(ids))
                ).all()
            )
        by_security = {row.security_id: row for row in rows}
        securities = (
            list(session.scalars(select(Security).where(Security.id.in_(ids))).all())
            if ids
            else []
        )
        sectors = {row.id: row.sector for row in securities}
        snapshots: list[CompanySnapshot] = []
        for line in analytics.allocation:
            row = by_security.get(line.security_id)
            sector = (sectors.get(line.security_id) or "").strip() or None
            if row is None:
                snapshots.append(CompanySnapshot(ticker=line.ticker, sector=sector))
                continue
            snapshots.append(
                CompanySnapshot(
                    ticker=line.ticker,
                    roe=row.roe,
                    pe_ratio=row.pe_ratio,
                    as_of=row.as_of,
                    provider=row.provider,
                    sector=sector,
                )
            )
        return snapshots

    def _holding_costs(self, analytics: AnalyticsOut) -> list[HoldingCost] | None:
        transactions = getattr(self.analytics, "transactions", None)
        if transactions is None:
            return None
        fills = [
            CostFill(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
                price=row.price,
            )
            for row in transactions.list_for_portfolio(analytics.portfolio_id)
        ]
        by_ticker = {
            row.ticker.upper(): row.avg_cost for row in average_cost_positions(fills)
        }
        return [
            HoldingCost(
                ticker=line.ticker,
                average_cost=by_ticker.get(line.ticker.upper()),
            )
            for line in analytics.allocation
        ]

    def _answer(
        self,
        prepared: AssistantEvidence,
        question: str,
        interpretation: str,
        interpretation_source: str,
    ) -> AssistantAnswer:
        evidence = prepared.evidence
        return AssistantAnswer(
            portfolio_id=prepared.portfolio_id,
            question=question,
            facts=[EvidenceItem.model_validate(item) for item in evidence["facts"]],
            metrics=[EvidenceItem.model_validate(item) for item in evidence["metrics"]],
            interpretation=interpretation,
            interpretation_source=interpretation_source,
            disclaimer=_DISCLAIMER,
        )

    def _can_fallback(self) -> bool:
        return (
            settings.ai_fallback_to_local
            and self.model.interpretation_source != "template"
        )


def _stored_headlines(
    quotes: QuoteStore,
    analytics: AnalyticsOut,
) -> list[tuple[str, str]]:
    reader = getattr(quotes, "get_news", None)
    if reader is None:
        return []
    found: list[tuple[str, str]] = []
    for line in analytics.allocation:
        try:
            if Decimal(line.quantity) <= 0:
                continue
        except Exception:
            continue
        try:
            rows = reader(line.ticker) or []
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows[:2]:
            if not isinstance(row, dict):
                continue
            headline = " ".join(str(row.get("headline") or "").split())
            if headline:
                found.append((line.ticker, headline[:180]))
    return found[:8]


def _detach_chart(evidence: dict) -> list:
    """Keep the stored value series for the page. The model does not receive it."""
    chart = evidence.pop("chart", None)
    return chart if isinstance(chart, list) else []


def _remember_direct(evidence: dict, question: str) -> None:
    focused = direct_answer(question, evidence)
    if focused:
        evidence["direct_answer"] = focused


def _reported_source(source: str, interpretation: str, evidence: dict) -> str:
    """A response that only restates the calculated answer is a template."""
    direct = str(evidence.get("direct_answer") or "")
    if direct and " ".join(interpretation.split()) == " ".join(direct.split()):
        return "template"
    return source


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def natural_screen(
    query: str,
    *,
    limit: int,
    offset: int,
    sort_by: ScreenSort,
    sort_direction: SortDirection,
    screening: ScreeningService,
    model: AssistantModel,
) -> tuple[str, ScreenResponse]:
    """Parse text into ScreenRequest, then run the existing screen query."""
    started = time.monotonic()
    try:
        parser, parsed = _parse_natural(query, model)
    finally:
        get_metrics().observe("ai.latency", time.monotonic() - started)
    # Pagination comes from the HTTP request, not from model output.
    bounded = parsed.model_copy(
        update={
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
        }
    )
    return parser, screening.screen(bounded)


_NOTE_WORDS = frozenset(
    {"ETF", "ETFS", "ROE", "USD", "PE", "AI", "THE", "AND", "FOR", "NOT"}
)


def screen_note(
    query: str,
    result: object,
    model: AssistantModel,
) -> tuple[str | None, str | None]:
    """A short reading of a finished screen. Filters stay as they were applied."""
    items = list(getattr(result, "items", []) or [])[:6]
    applied = getattr(result, "applied", None)
    payload = {
        "query": query,
        "applied": {
            "sector": getattr(applied, "sector", None),
            "asset_type": getattr(applied, "asset_type", None),
            "search": getattr(applied, "search", None),
            "total": getattr(result, "total", None),
        },
        "results": [
            {
                "ticker": item.ticker,
                "name": item.name,
                "asset_type": getattr(item, "asset_type", ""),
            }
            for item in items
        ],
    }
    tickers = {str(item.ticker).upper() for item in items}
    try:
        text = model.comment_on_screen(payload)
        source = model.interpretation_source
    except Exception:
        get_metrics().increment("ai.errors")
        text = LocalAssistant().comment_on_screen(payload)
        source = LocalAssistant.interpretation_source
    cleaned = _accepted_screen_note(text, tickers)
    if cleaned is None:
        cleaned = _accepted_screen_note(
            LocalAssistant().comment_on_screen(payload),
            tickers,
        )
        source = LocalAssistant.interpretation_source
    if not cleaned:
        return None, None
    return cleaned, source


def _accepted_screen_note(text: str, tickers: set[str]) -> str | None:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return None
    found = set(re.findall(r"\b[A-Z]{1,5}\b", cleaned))
    if found - tickers - _NOTE_WORDS:
        return None
    return cleaned


def _parse_natural(
    query: str,
    model: AssistantModel,
) -> tuple[str, ScreenRequest]:
    """Rules win when they understand the sentence, so a model cannot invent one."""
    try:
        return LocalAssistant.screen_parser, parse_screen_text(query)
    except AppError:
        if model.screen_parser == LocalAssistant.screen_parser:
            raise
    try:
        parsed = model.parse_screen(query)
    except Exception:
        get_metrics().increment("ai.errors")
        if not settings.ai_fallback_to_local:
            raise
        return LocalAssistant.screen_parser, LocalAssistant().parse_screen(query)
    return model.screen_parser, drop_unmentioned(query, parsed)
