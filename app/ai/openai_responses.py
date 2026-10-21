from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from app.ai.evidence import finalize_interpretation
from app.ai.openai_compatible import (
    _EXPLAIN_INSTRUCTION,
    _IDEA_INSTRUCTION,
    _INTERPRET_INSTRUCTION,
    _NEWS_INSTRUCTION,
    _SCREEN_INSTRUCTION,
    _SCREEN_NOTE_INSTRUCTION,
    _STORY_INSTRUCTION,
    _explain_fields,
    _load_json_object,
    _news_briefs,
    _story_fields,
    _story_text,
)
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


class OpenAIResponsesModel:
    """Native OpenAI Responses API client using strict structured outputs."""

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
        raw = self._complete(
            _EXPLAIN_INSTRUCTION,
            json.dumps({"term": term, "evidence": evidence}),
            schema_name="term_explanation",
            schema=explain_json_schema(),
        )
        return _explain_fields(raw)

    def interpret(self, question: str, evidence: dict) -> str:
        raw = self._complete(
            _INTERPRET_INSTRUCTION,
            json.dumps({"question": question, "evidence": evidence}),
            schema_name="assistant_interpretation",
            schema=interpretation_json_schema(),
        )
        return finalize_interpretation(_interpretation_text(raw), evidence)

    def stream_interpret(self, question: str, evidence: dict) -> Iterator[str]:
        payload = self._payload(
            _INTERPRET_INSTRUCTION,
            json.dumps({"question": question, "evidence": evidence}),
            schema_name="assistant_interpretation",
            schema=interpretation_json_schema(),
        )
        payload["stream"] = True
        fragments: list[str] = []
        completed = False
        try:
            with self._stream(payload) as response:
                if response.status_code != 200:
                    raise AppError("Language model request failed", status_code=502)
                for event, data in _responses_sse(response.iter_lines()):
                    event_type = (
                        data.get("type") if isinstance(data.get("type"), str) else event
                    )
                    if event_type == "response.output_text.delta":
                        delta = data.get("delta")
                        if isinstance(delta, str):
                            fragments.append(delta)
                    elif event_type == "response.completed":
                        completed = True
                    elif event_type in {
                        "error",
                        "response.failed",
                        "response.incomplete",
                    }:
                        raise AppError(
                            "Language model streaming request failed",
                            status_code=502,
                        )
        except httpx.HTTPError as exc:
            raise AppError("Language model request failed", status_code=502) from exc
        if not completed:
            raise AppError(
                "Language model returned an incomplete stream",
                status_code=502,
            )
        # Strict output is buffered until its complete object validates. This keeps
        # malformed or non-evidence output from reaching the caller.
        try:
            raw = _load_json_object("".join(fragments))
            text = _interpretation_text(raw)
        except (TypeError, ValueError) as exc:
            raise AppError(
                "Language model returned an unreadable response",
                status_code=502,
            ) from exc
        yield finalize_interpretation(text, evidence)

    def _complete(
        self,
        instruction: str,
        user: str,
        *,
        schema_name: str,
        schema: dict,
    ) -> dict:
        logger.info("ai_request", extra={"model": self._model, "api": "responses"})
        response = self._post(
            self._payload(
                instruction,
                user,
                schema_name=schema_name,
                schema=schema,
            )
        )
        if response.status_code != 200:
            raise AppError("Language model request failed", status_code=502)
        try:
            return _load_json_object(_response_text(response.json()))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError(
                "Language model returned an unreadable response",
                status_code=502,
            ) from exc

    def _payload(
        self,
        instruction: str,
        user: str,
        *,
        schema_name: str,
        schema: dict,
    ) -> dict:
        return {
            "model": self._model,
            "instructions": instruction,
            "input": user,
            "temperature": 0,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    def _post(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/responses"
        if self._client is not None:
            return self._client.post(url, json=payload, headers=headers)
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(url, json=payload, headers=headers)

    @contextmanager
    def _stream(self, payload: dict) -> Iterator[httpx.Response]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }
        url = f"{self._base_url}/responses"
        if self._client is not None:
            request = self._client.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
            )
            with request as response:
                yield response
            return
        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                yield response


def _response_text(body: dict) -> str:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text
    for output in body.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("Responses API returned no output text")


def _interpretation_text(raw: dict) -> str:
    if set(raw) != {"interpretation"}:
        raise AppError(
            "Language model returned an invalid interpretation object",
            status_code=502,
        )
    text = raw["interpretation"]
    if not isinstance(text, str) or not text.strip():
        raise AppError("Language model returned no interpretation", status_code=502)
    return text.strip()


def _responses_sse(lines: Iterator[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Parse Responses API SSE frames without assuming network chunk boundaries."""
    event = "message"
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                payload = "\n".join(data_lines)
                if payload != "[DONE]":
                    try:
                        value = json.loads(payload)
                    except ValueError as exc:
                        raise AppError(
                            "Language model returned an unreadable stream",
                            status_code=502,
                        ) from exc
                    if not isinstance(value, dict):
                        raise AppError(
                            "Language model returned an unreadable stream",
                            status_code=502,
                        )
                    yield event, value
            event = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        payload = "\n".join(data_lines)
        if payload != "[DONE]":
            try:
                value = json.loads(payload)
            except ValueError as exc:
                raise AppError(
                    "Language model returned an unreadable stream",
                    status_code=502,
                ) from exc
            if isinstance(value, dict):
                yield event, value
