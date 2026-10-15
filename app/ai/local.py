from __future__ import annotations

import re
from collections.abc import Iterator

from app.ai.evidence import render_interpretation
from app.ai.parsing import parse_screen_text
from app.schemas.screening import ScreenRequest


class LocalAssistant:
    """Rules and a template. Used when no language-model API is configured."""

    screen_parser = "rules"
    interpretation_source = "template"

    def parse_screen(self, query: str) -> ScreenRequest:
        return parse_screen_text(query)

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
            "what": f"{term} is not a figure FinSight calculates on its own.",
            "example": "A language model can add one short hypothetical example.",
            "yours": yours,
            "watch": "No formula is invented here. Not a forecast.",
        }

    def interpret(self, question: str, evidence: dict) -> str:
        # A recognized question is answered from evidence. Anything else uses
        # the full template, which ignores the wording so it cannot add facts.
        focused = answer_from_evidence(question, evidence)
        if focused is not None:
            return focused
        return render_interpretation(evidence)

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        yield from _text_chunks(self.interpret(question, evidence))


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
    text = " ".join(question.lower().split())
    metrics = {item["name"]: item["value"] for item in evidence.get("metrics", [])}
    if _mentions(text, "largest", "biggest", "concentration", "weight"):
        ticker = metrics.get("largest_weight_ticker", "undefined")
        weight = metrics.get("largest_weight", "undefined")
        if ticker == "undefined":
            return "No position weight is stored."
        return f"The largest current weight is {ticker} at {weight}."
    if _mentions(text, "today", "gainer", "loser", "mover", "day move"):
        gainer = metrics.get("largest_gainer")
        loser = metrics.get("largest_loser")
        if not gainer and not loser:
            return "No live day move is stored."
        return (
            f"The strongest day move is {gainer}. "
            f"The weakest day move is {loser}."
        )
    if _mentions(text, "return", "performance", "how did"):
        value = metrics.get("total_return", "undefined")
        return f"Full-sample total return is {value}."
    if _mentions(text, "volatility", "risk", "drawdown"):
        summary = render_interpretation(evidence)
        return summary.split(". ")[0].rstrip(".") + "."
    if _mentions(text, "holding", "holdings", "positions"):
        positions = [
            item["value"]
            for item in evidence.get("facts", [])
            if item["name"].startswith("position:")
        ]
        if not positions:
            return "No current holdings are stored."
        return "Current holdings: " + "; ".join(positions) + "."
    return None


def _mentions(text: str, *phrases: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(phrase)}\b", text) is not None for phrase in phrases
    )


def _text_chunks(text: str, size: int = 48) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]
