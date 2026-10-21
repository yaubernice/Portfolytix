from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator

import httpx

from app.ai.evidence import finalize_interpretation
from app.ai.local import _text_chunks, headline_brief
from app.ai.parsing import screen_from_model_json
from app.ai.structured import (
    explain_json_schema,
    idea_json_schema,
    interpretation_json_schema,
    news_json_schema,
    screen_json_schema,
    story_json_schema,
)
from app.core.exceptions import AppError
from app.schemas.screening import ScreenRequest

logger = logging.getLogger(__name__)

_SCREEN_INSTRUCTION = (
    "Return one JSON object and no other keys. "
    "If the sentence names a number and a metric, set that metric. "
    "Do not return only a sector when a number is present. "
    "Do not invent a sector the sentence did not name. "
    '"above", "over", "more than", "at least", and "higher than" set the min '
    "field only. "
    '"below", "under", "less than", "at most", and "lower than" set the max '
    "field only. "
    'Example: "companies with more than 40% ROE" -> {"roe_min":"0.40"}. '
    '"technology companies with ROE above 15%" -> '
    '{"sector":"technology","roe_min":"0.15"}. '
    'Example: "P/E below 25" -> {"pe_max":"25"}. '
    "Put communication services, consumer discretionary, financial services, "
    "basic materials, technology, healthcare, financials, industrials, and "
    "energy in sector, never industry. "
    "ETF, ETFs, and exchange-traded funds set asset_type to etf. "
    "A mutual fund sets asset_type to fund. Do not put ETF in sector. "
    "A ticker or product name such as VOO or Hang Seng sets search to that "
    "text. Do not invent a sector, a search, or a number the sentence did "
    "not state. "
    "Ratio fields (roe, revenue_growth, profit_margin, dividend_yield, roa, "
    'earnings_growth) are decimals: 40% is "0.40". '
    "P/E, beta, price_to_book, and price_to_sales stay multiples. "
    "market_cap, revenue, eps, and ebitda are USD."
)
_EXPLAIN_INSTRUCTION = (
    "Return one JSON object with keys what, formula, example, yours, watch. "
    "The reader is new to finance. Each value is one short sentence, "
    "about 20 words, with no extra paragraph. "
    "what: what the word means. "
    "formula: the standard formula, or empty if you are not sure. "
    "Do not invent a formula. "
    "example: one hypothetical number, and say it is hypothetical. "
    "yours: one sentence using a figure from the evidence, or say no "
    "portfolio figure applies. "
    "watch: one limitation. Not advice and not a forecast. "
    "Do not invent prices, holdings, or dates."
)
_STORY_INSTRUCTION = (
    'Return one JSON object {"about": string, "points": [strings]}. '
    "The reader is new to finance and opened one story. "
    "about: two short sentences saying what the story is about. "
    "points: up to three short facts from the article, one sentence each. "
    "Use only the article text. "
    "Do not add numbers, prices, or events that are not written there. "
    "Do not say whether to buy or sell. Do not predict."
)
_NEWS_INSTRUCTION = (
    'Return one JSON object {"briefs": [one string per story, same order]}. '
    "The reader is new to finance. Each string is one short sentence, "
    "about 20 words, restating that headline in everyday words. "
    "Keep the same company names and the same direction: up stays up, "
    "down stays down. "
    "Do not replace a name with a description of what it is. "
    "Do not add numbers, prices, dates, or causes that are not written there. "
    "Do not say whether to buy or sell. Do not predict. "
    "If a phrase is unclear, keep the headline's own words."
)
_SCREEN_NOTE_INSTRUCTION = (
    'Return one JSON object {"commentary": string}. '
    "One or two short sentences about this screen. "
    "Use only the query, the applied filters, and the result names given. "
    "Do not add a ticker, a company, or a number that is not in that list. "
    "Do not say to buy or sell. Do not predict a price."
)
_IDEA_INSTRUCTION = (
    'Return one JSON object {"commentary": string}. '
    "One or two short sentences about these stored companies. "
    "Use only the points given. "
    "Do not add a number, a price, a forecast, or a buy or sell instruction."
)
_INTERPRET_INSTRUCTION = (
    'Return one JSON object {"interpretation": string}. '
    "Answer the question in the first sentence, for a reader who is new "
    "to finance. Use short sentences. "
    "Personal portfolio numbers must come from the evidence. "
    "If direct_answer is present, start with it and do not change its numbers. "
    "Cite a supporting item as [e3] only when that id is in the evidence. "
    "Do not invent an id. "
    "A missing company figure such as ROE is not a short portfolio-return "
    "history. Do not say historical returns are required to calculate "
    "company ROE. "
    "A market-value-weighted average ROE is a summary of company ratios, "
    "not a portfolio return. "
    "If a value is unavailable, name the missing input and what is available. "
    "Do not treat a missing value as zero. "
    "Say the as-of date when the evidence has one. "
    "Do not invent prices, holdings, dates, headlines, or results. "
    "If the question asks about news or a future period, use the stored "
    "headlines and the current holdings. Say which holding a headline names. "
    "Do not invent a future return or a price target. "
    "Do not give an order to buy or sell. "
    "If direct_answer says a judgment is not in the stored evidence, "
    "do not add industry knowledge, a supplier, a policy, or a buy or "
    "sell rule from anywhere else. "
    "One limitation is enough. Do not repeat a disclaimer in every sentence. "
    "If direct_answer already has line breaks, keep them. "
    "Do not copy a headline that is already written there."
)


class OpenAICompatibleModel:
    """Chat-completions client. The request body is text, never a DB session."""

    screen_parser = "llm"
    interpretation_source = "llm"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise AppError("AI_API_KEY is empty", status_code=400)
        self._api_key = api_key.strip()
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    def comment_on_ideas(self, notes: list[dict]) -> str:
        raw = self._complete(
            _IDEA_INSTRUCTION,
            json.dumps({"companies": notes[:6]}),
            schema_name="idea_commentary",
            schema=idea_json_schema(),
        )
        text = raw.get("commentary")
        if not isinstance(text, str) or not text.strip():
            raise AppError("Language model returned no idea note", status_code=502)
        return " ".join(text.split())

    def comment_on_screen(self, payload: dict) -> str:
        raw = self._complete(
            _SCREEN_NOTE_INSTRUCTION,
            json.dumps(payload),
            schema_name="screen_note",
            schema=idea_json_schema(),
        )
        text = raw.get("commentary")
        if not isinstance(text, str) or not text.strip():
            raise AppError("Language model returned no screen note", status_code=502)
        return " ".join(text.split())

    def parse_screen(self, query: str) -> ScreenRequest:
        return screen_from_model_json(
            self._complete(
                _SCREEN_INSTRUCTION,
                query,
                schema_name="screen_request",
                schema=screen_json_schema(),
            )
        )

    def summarize_story(self, headline: str, text: str) -> dict:
        raw = self._complete(
            _STORY_INSTRUCTION,
            json.dumps({"headline": headline, "article": text[:2400]}),
            schema_name="story_summary",
            schema=story_json_schema(),
        )
        return _story_fields(raw, text)

    def summarize_news(self, stories: list[dict]) -> list[str]:
        if not stories:
            return []
        raw = self._complete(
            _NEWS_INSTRUCTION,
            json.dumps({"stories": [_story_text(story) for story in stories]}),
            schema_name="news_briefs",
            schema=news_json_schema(),
        )
        return _news_briefs(raw, stories)

    def explain_term(self, term: str, evidence: dict) -> dict:
        payload = json.dumps({"term": term, "evidence": evidence})
        raw = self._complete(
            _EXPLAIN_INSTRUCTION,
            payload,
            schema_name="term_explanation",
            schema=explain_json_schema(),
        )
        return _explain_fields(raw)

    def interpret(self, question: str, evidence: dict) -> str:
        payload = json.dumps({"question": question, "evidence": evidence})
        raw = self._complete(
            _INTERPRET_INSTRUCTION,
            payload,
            schema_name="assistant_interpretation",
            schema=interpretation_json_schema(),
        )
        text = raw.get("interpretation")
        if not isinstance(text, str) or not text.strip():
            raise AppError(
                "Language model returned no interpretation",
                status_code=502,
            )
        return finalize_interpretation(text.strip(), evidence)

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        yield from _text_chunks(self.interpret(question, evidence))

    def _complete(
        self,
        instruction: str,
        user: str,
        *,
        schema_name: str,
        schema: dict,
    ) -> dict:
        # The key stays in the header. It is not written to the log.
        logger.info("ai_request", extra={"model": self._model})
        # json_object, not a strict schema: smaller local models fill the
        # wrong bound when every field is listed as required. Callers still
        # pass the schema so the Responses client and this client share one
        # signature.
        _ = (schema_name, schema)
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": user},
            ],
        }
        response = self._post(payload)
        if response.status_code != 200:
            raise AppError("Language model request failed", status_code=502)
        try:
            body = response.json()
            message = body["choices"][0]["message"]
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                # Some OpenRouter models put the JSON in the reasoning field.
                reasoning = message.get("reasoning")
                content = reasoning if isinstance(reasoning, str) else ""
            return _load_json_object(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError(
                "Language model returned an unreadable response",
                status_code=502,
            ) from exc

    def _post(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        if self._client is not None:
            return self._client.post(url, json=payload, headers=headers)
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, json=payload, headers=headers)


def _story_fields(raw: dict, article: str) -> dict:
    about = raw.get("about", "")
    about = _two_sentences(about) if isinstance(about, str) else ""
    source = {"headline": article, "summary": ""}
    if not about or _adds_number(about, source):
        raise AppError("Language model returned no story summary", status_code=502)
    points: list[str] = []
    values = raw.get("points")
    if isinstance(values, list):
        for value in values:
            line = _one_sentence(value) if isinstance(value, str) else ""
            if not line or _adds_number(line, source):
                continue
            points.append(line)
            if len(points) == 3:
                break
    return {"about": about, "points": points}


def _two_sentences(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = " ".join(parts[:2])
    if len(kept) > 320:
        kept = kept[:317].rsplit(" ", 1)[0] + "…"
    return kept


def _story_text(story: dict) -> dict:
    return {
        "headline": str(story.get("headline") or ""),
        "summary": str(story.get("summary") or ""),
        "source": str(story.get("source") or ""),
        "ticker": str(story.get("ticker") or ""),
    }


def _news_briefs(raw: dict, stories: list[dict]) -> list[str]:
    values = raw.get("briefs")
    if not isinstance(values, list) or len(values) != len(stories):
        raise AppError("Language model returned no news summary", status_code=502)
    briefs: list[str] = []
    for story, value in zip(stories, values, strict=True):
        text = _one_sentence(value) if isinstance(value, str) else ""
        text = _drop_unrelated_but(text, story)
        if (
            not text
            or _adds_number(text, story)
            or _changes_direction(text, story)
            or _mentions_other_story(text, story, stories)
            or _too_far(text, story)
        ):
            text = headline_brief(story)
        briefs.append(text)
    return briefs


_STOP_WORDS = {
    "about",
    "after",
    "although",
    "and",
    "are",
    "been",
    "before",
    "but",
    "each",
    "from",
    "have",
    "into",
    "more",
    "than",
    "that",
    "their",
    "them",
    "they",
    "this",
    "with",
    "would",
}


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z']{3,}", text.lower())
    return {word for word in words if word not in _STOP_WORDS}


def _mentions_other_story(text: str, story: dict, stories: list[dict]) -> bool:
    own = _content_words(f"{story.get('headline', '')} {story.get('summary', '')}")
    others: set[str] = set()
    for item in stories:
        if item is story:
            continue
        others.update(
            _content_words(f"{item.get('headline', '')} {item.get('summary', '')}")
        )
    borrowed = _content_words(text) & others
    return bool(borrowed - own)


def _drop_unrelated_but(text: str, story: dict) -> str:
    parts = re.split(r",\s+but\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return text
    source = _content_words(f"{story.get('headline', '')} {story.get('summary', '')}")
    if _content_words(parts[1]) <= source:
        return text
    kept = parts[0].rstrip()
    if kept and not kept.endswith((".", "…")):
        kept += "."
    return kept


_UP_WORDS = (
    "rise",
    "rises",
    "rose",
    "rising",
    "gain",
    "gains",
    "gained",
    "climb",
    "climbs",
    "rally",
    "rallies",
    "surge",
    "surges",
    "jump",
    "jumps",
    "recover",
    "recovers",
    "recovered",
    "recovery",
    "up",
    "higher",
)
_DOWN_WORDS = (
    "slip",
    "slips",
    "slipped",
    "dive",
    "dives",
    "dived",
    "fall",
    "falls",
    "fell",
    "drop",
    "drops",
    "dropped",
    "stung",
    "sink",
    "sinks",
    "tumble",
    "tumbles",
    "plunge",
    "plunges",
    "down",
    "lower",
)


def _changes_direction(text: str, story: dict) -> bool:
    source = f"{story.get('headline', '')} {story.get('summary', '')}".lower()
    brief = text.lower()
    if _has_word(brief, _UP_WORDS) and not _has_word(source, _UP_WORDS):
        return True
    return _has_word(brief, _DOWN_WORDS) and not _has_word(source, _DOWN_WORDS)


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{word}\b", text) is not None for word in words)


def _too_far(text: str, story: dict) -> bool:
    """A restatement should still be made of the headline's own words."""
    source = _content_words(f"{story.get('headline', '')} {story.get('summary', '')}")
    words = _content_words(text)
    if not words:
        return True
    return len(words & source) * 2 < len(words)


def _adds_number(text: str, story: dict) -> bool:
    source = f"{story.get('headline', '')} {story.get('summary', '')}"
    allowed = set(re.findall(r"\d+(?:\.\d+)?", source.replace(",", "")))
    for number in re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")):
        if number not in allowed:
            return True
    return False


def _one_sentence(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return ""
    for mark in (". ", "? ", "! "):
        if mark in text:
            text = text.split(mark)[0] + mark.strip()
            break
    if len(text) > 160:
        text = text[:157].rsplit(" ", 1)[0] + "…"
    return text


def _explain_fields(raw: dict) -> dict:
    what = raw.get("what")
    if not isinstance(what, str) or not what.strip():
        legacy = raw.get("explanation")
        what = legacy if isinstance(legacy, str) else ""
    if not what.strip():
        raise AppError("Language model returned no explanation", status_code=502)
    formula = raw.get("formula", "")
    if not isinstance(formula, str):
        formula = ""

    def line(name: str) -> str:
        value = raw.get(name, "")
        return _one_sentence(value) if isinstance(value, str) else ""

    return {
        "what": _one_sentence(what),
        "formula": " ".join(formula.split())[:120],
        "example": line("example"),
        "yours": line("yours"),
        "watch": line("watch"),
    }


def _load_json_object(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("model JSON must be an object")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model JSON must be an object")
    return value
