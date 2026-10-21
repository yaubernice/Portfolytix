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

    def summarize_news(self, stories: list[dict]) -> list[str]:
        """One short line per story, using only that story's own text."""

    def summarize_story(self, headline: str, text: str) -> dict:
        """Say what one article is about. Use only that article's text."""

    def comment_on_ideas(self, notes: list[dict]) -> str:
        """One short note from stored idea points. No new figures."""

    def comment_on_screen(self, payload: dict) -> str:
        """One short note from a finished screen. No new companies."""

    def interpret(self, question: str, evidence: dict) -> str:
        """Phrase an answer from evidence the application already computed."""

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        """Yield safe interpretation text in display-sized chunks."""
