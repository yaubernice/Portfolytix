from __future__ import annotations

import re
from collections.abc import Iterator

from app.ai.evidence import (
    direct_answer,
    finalize_interpretation,
    render_interpretation,
)
from app.ai.parsing import parse_screen_text
from app.schemas.screening import ScreenRequest


class LocalAssistant:
    """Rules and a template. Used when no language-model API is configured."""

    screen_parser = "rules"
    interpretation_source = "template"

    def parse_screen(self, query: str) -> ScreenRequest:
        return parse_screen_text(query)

    def comment_on_ideas(self, notes: list[dict]) -> str:
        lines = []
        for note in notes[:6]:
            points = [str(point) for point in note.get("points") or [] if point]
            if points:
                lines.append(f"{note.get('ticker', '')}: {points[0]}")
        return " ".join(lines)

    def comment_on_screen(self, payload: dict) -> str:
        applied = payload.get("applied") or {}
        bits = [
            f"{name} {applied[name]}"
            for name in ("sector", "asset_type", "search")
            if applied.get(name)
        ]
        tickers = [
            str(row.get("ticker") or "")
            for row in (payload.get("results") or [])[:5]
            if row.get("ticker")
        ]
        if not bits and not tickers:
            return ""
        sentence = "The screen used " + ", ".join(bits) + "." if bits else ""
        if tickers:
            listed = ", ".join(tickers)
            sentence = (
                f"{sentence} The first stored names are {listed}."
                if sentence
                else f"The first stored names are {listed}."
            )
        return " ".join(sentence.split())

    def summarize_news(self, stories: list[dict]) -> list[str]:
        return [headline_brief(story) for story in stories]

    def summarize_story(self, headline: str, text: str) -> dict:
        sentences = _sentences(text)
        about = " ".join(sentences[:2])
        points = sentences[2:5] or sentences[:1]
        return {"about": about[:400], "points": points[:3], "headline": headline}

    def explain_term(self, term: str, evidence: dict) -> dict:
        # No invented formula and no invented portfolio number. A configured
        # model writes the fresh explanation; this template only fills in.
        shown = [
            f"{item['label']} is {item['value']}"
            for item in evidence.get("facts", [])
            if item.get("label") and item.get("value")
        ][:1]
        yours = "No portfolio figure is tied to this phrase."
        if shown:
            yours = _one_local_line(shown[0])
        elif evidence.get("note"):
            yours = _one_local_line(str(evidence["note"]))
        return {
            "formula": "",
            "what": (
                f"{term} is not a stored metric, so no other figure is used "
                "in its place."
            ),
            "example": "",
            "yours": yours,
            "watch": "Not a forecast.",
        }

    def interpret(self, question: str, evidence: dict) -> str:
        # A recognized question is answered from evidence. Anything else uses
        # the full template, which ignores the wording so it cannot add facts.
        focused = evidence.get("direct_answer") or direct_answer(question, evidence)
        text = focused if focused else render_interpretation(evidence)
        payload = evidence
        if focused and not evidence.get("direct_answer"):
            payload = {**evidence, "direct_answer": focused}
        return finalize_interpretation(text, payload)

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        yield from _text_chunks(self.interpret(question, evidence))


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [part.strip() for part in parts if part.strip()]


def stored_headline_line(headline: str, summary: str) -> str:
    """One line from stored story text. No stored text stays an absence."""
    clean_headline = " ".join(str(headline or "").split())
    clean_summary = " ".join(str(summary or "").split())
    if clean_summary and clean_summary.lower() != clean_headline.lower():
        brief = headline_brief({"headline": clean_headline, "summary": clean_summary})
        if brief and brief.lower().rstrip(".") != clean_headline.lower().rstrip("."):
            return brief
    return "No summary is stored for this headline."


def headline_brief(story: dict) -> str:
    """Use the provider summary, or the headline. Add no new facts."""
    summary = " ".join(str(story.get("summary") or "").split())
    headline = " ".join(str(story.get("headline") or "").split())
    if summary:
        return _one_local_line(summary)
    if not headline:
        return "No headline text was available."
    return _one_local_line(headline)


def _one_local_line(value: str) -> str:
    text = " ".join(value.split())
    if ". " in text:
        text = text.split(". ")[0] + "."
    if len(text) > 140:
        text = text[:137].rsplit(" ", 1)[0] + "…"
    if text and not text.endswith((".", "…")):
        text += "."
    return text


def answer_from_evidence(question: str, evidence: dict) -> str | None:
    """Pick stored facts for a few questions. Unrecognized wording returns None."""
    return direct_answer(question, evidence)


def _text_chunks(text: str, size: int = 48) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]
