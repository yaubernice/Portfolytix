from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from app.ai.evidence import attach_live_moves, build_evidence
from app.ai.local import LocalAssistant
from app.ai.provider import AssistantModel
from app.core.config import settings
from app.core.metrics import get_metrics
from app.quotes.store import QuoteStore
from app.schemas.assistant import AssistantAnswer, EvidenceItem
from app.schemas.screening import ScreenResponse, ScreenSort, SortDirection
from app.services.analytics_service import AnalyticsService
from app.services.screening_service import ScreeningService

_DISCLAIMER = (
    "Not investment advice. Facts come from stored transactions and prices. "
    "Metrics are FinSight calculations. The interpretation only restates "
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
        finally:
            get_metrics().observe("ai.latency", time.monotonic() - started)
        return self._answer(prepared, question, interpretation, source)

    def prepare(self, portfolio_id: UUID) -> AssistantEvidence:
        # Ownership and calculations happen here. The model is not involved.
        analytics = self.analytics.get_analytics(portfolio_id)
        evidence = build_evidence(analytics)
        if self.quotes is not None:
            evidence = attach_live_moves(
                evidence,
                analytics,
                self.quotes.snapshot(),
            )
        return AssistantEvidence(portfolio_id=portfolio_id, evidence=evidence)

    def stream(
        self,
        prepared: AssistantEvidence,
        question: str,
    ) -> Iterator[str]:
        evidence_event = {
            "portfolio_id": str(prepared.portfolio_id),
            "question": question,
            "facts": prepared.evidence["facts"],
            "metrics": prepared.evidence["metrics"],
            "interpretation_source": self.model.interpretation_source,
            "disclaimer": _DISCLAIMER,
        }
        yield _sse("evidence", evidence_event)
        started = time.monotonic()
        try:
            for chunk in self.model.stream_interpret(question, prepared.evidence):
                if chunk:
                    yield _sse("text", {"delta": chunk})
            yield _sse("done", {"done": True})
        except Exception:
            get_metrics().increment("ai.errors")
            if self._can_fallback():
                fallback = LocalAssistant()
                evidence_event["interpretation_source"] = fallback.interpretation_source
                yield _sse("evidence", evidence_event)
                for chunk in fallback.stream_interpret(question, prepared.evidence):
                    yield _sse("text", {"delta": chunk})
                yield _sse("done", {"done": True, "fallback": True})
            else:
                yield _sse("error", {"message": "Assistant interpretation failed"})
        finally:
            get_metrics().observe("ai.latency", time.monotonic() - started)

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
            metrics=[
                EvidenceItem.model_validate(item) for item in evidence["metrics"]
            ],
            interpretation=interpretation,
            interpretation_source=interpretation_source,
            disclaimer=_DISCLAIMER,
        )

    def _can_fallback(self) -> bool:
        return (
            settings.ai_fallback_to_local
            and self.model.interpretation_source != "template"
        )


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
    parser = model.screen_parser
    try:
        parsed = model.parse_screen(query)
    except Exception:
        get_metrics().increment("ai.errors")
        if not (
            settings.ai_fallback_to_local
            and model.screen_parser != LocalAssistant.screen_parser
        ):
            raise
        fallback = LocalAssistant()
        parsed = fallback.parse_screen(query)
        parser = fallback.screen_parser
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
