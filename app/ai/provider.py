from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from app.schemas.screening import ScreenRequest


class AssistantModel(Protocol):
    """Turns text into structured objects. No session, engine, or SQL."""

    screen_parser: str
    interpretation_source: str

    def parse_screen(self, query: str) -> ScreenRequest:
        """Return a validated screen. Callers execute it themselves."""

    def explain_term(self, term: str, evidence: dict) -> dict:
        """Explain any phrase. Return explanation and formula strings."""

    def interpret(self, question: str, evidence: dict) -> str:
        """Phrase an answer from evidence the application already computed."""

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        """Yield safe interpretation text in display-sized chunks."""
