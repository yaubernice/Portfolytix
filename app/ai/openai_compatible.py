from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import httpx

from app.ai.local import _text_chunks
from app.ai.parsing import screen_from_model_json
from app.ai.structured import interpretation_json_schema, screen_json_schema
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
    "Put communication services, consumer discretionary, technology, "
    "healthcare, financials, industrials, and energy in sector, never "
    "industry. "
    "Ratio fields (roe, revenue_growth, profit_margin, dividend_yield, roa, "
    'earnings_growth) are decimals: 40% is "0.40". '
    "P/E, beta, price_to_book, and price_to_sales stay multiples. "
    "market_cap, revenue, eps, and ebitda are USD."
)
_INTERPRET_INSTRUCTION = (
    'Return one JSON object {"interpretation": string}. '
    "Write two or three sentences that answer the question using only the "
    "evidence JSON. Quote the relevant figures. "
    "If the evidence has no figure for the question, say that it is not in "
    "the evidence. Do not invent prices, holdings, or dates."
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

    def parse_screen(self, query: str) -> ScreenRequest:
        return screen_from_model_json(
            self._complete(
                _SCREEN_INSTRUCTION,
                query,
                schema_name="screen_request",
                schema=screen_json_schema(),
            )
        )

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
        return text.strip()

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
            content = body["choices"][0]["message"]["content"]
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


def _load_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("model JSON must be an object")
    return value
