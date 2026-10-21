from __future__ import annotations

import re
from decimal import Decimal

from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.screening import CRITERIA_FIELDS, ScreenRequest

# Longer phrases first so "communication services" wins over a shorter token.
_SECTORS: tuple[tuple[str, str], ...] = (
    ("communication services", "communication services"),
    ("consumer discretionary", "consumer discretionary"),
    ("financial services", "financial services"),
    ("basic materials", "basic materials"),
    ("technology", "technology"),
    ("healthcare", "healthcare"),
    ("financials", "financials"),
    ("industrials", "industrials"),
    ("energy", "energy"),
)

_TYPOS: tuple[tuple[str, str], ...] = (
    ("tehcnoogy", "technology"),
    ("technolgy", "technology"),
    ("techology", "technology"),
    ("tecnology", "technology"),
    ("technoloy", "technology"),
    ("healtcare", "healthcare"),
    ("health care", "healthcare"),
    ("finacials", "financials"),
    ("finanicals", "financials"),
)

_ASSET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bexchange[- ]traded(?: funds?)?\b"), "etf"),
    (re.compile(r"\betfs?\b"), "etf"),
    (re.compile(r"\bmutual funds?\b"), "fund"),
    (re.compile(r"\bindex funds?\b"), "fund"),
    (re.compile(r"\b(?:indices|indexes)\b"), "index"),
)

_STOP = frozenset(
    {
        "a",
        "above",
        "all",
        "an",
        "and",
        "at",
        "below",
        "cap",
        "companies",
        "company",
        "dividend",
        "earnings",
        "find",
        "for",
        "greater",
        "growth",
        "higher",
        "in",
        "least",
        "less",
        "list",
        "lower",
        "margin",
        "market",
        "me",
        "more",
        "most",
        "my",
        "of",
        "or",
        "over",
        "pe",
        "percent",
        "please",
        "price",
        "profit",
        "ratio",
        "revenue",
        "roe",
        "screen",
        "securities",
        "security",
        "share",
        "shares",
        "show",
        "some",
        "stock",
        "stocks",
        "than",
        "that",
        "the",
        "these",
        "those",
        "under",
        "with",
        "yield",
    }
)
_SQL_WORDS = frozenset(
    {
        "alter",
        "delete",
        "drop",
        "from",
        "insert",
        "select",
        "table",
        "union",
        "update",
        "where",
    }
)

_MIN_WORD = r"(?:above|over|greater than|more than|higher than|at least|>=|>)"
_MAX_WORD = r"(?:below|under|less than|lower than|at most|<=|<)"
_ROE_MIN = re.compile(
    rf"roe\s*{_MIN_WORD}\s*(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)
_ROE_MAX = re.compile(
    rf"roe\s*{_MAX_WORD}\s*(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)
_PE_MAX = re.compile(
    rf"(?:p/?e|price to earnings)\s*(?:ratio\s*)?{_MAX_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)"
)
_PE_MIN = re.compile(
    rf"(?:p/?e|price to earnings)\s*(?:ratio\s*)?{_MIN_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)"
)
_GROWTH_MIN = re.compile(
    rf"revenue growth\s*{_MIN_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)
_GROWTH_MAX = re.compile(
    rf"revenue growth\s*{_MAX_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)
_MCAP_MIN = re.compile(
    rf"market cap\s*{_MIN_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>billion|bn|million|mm)?"
)
_MCAP_MAX = re.compile(
    rf"market cap\s*{_MAX_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>billion|bn|million|mm)?"
)
_DIV_MIN = re.compile(
    rf"dividend yield\s*{_MIN_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)
_MARGIN_MIN = re.compile(
    rf"profit margin\s*{_MIN_WORD}\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>%|percent)?"
)


def parse_screen_text(query: str) -> ScreenRequest:  # filters object
    """Map a narrow English pattern onto ScreenRequest. No SQL is built."""
    text = _normalize(query)
    payload: dict[str, Decimal | str] = {}
    sector, without_sector = _sector_match(text)
    if sector is not None:
        payload["sector"] = sector
    asset_type, _without_asset = _asset_match(text)
    if asset_type is not None:
        payload["asset_type"] = asset_type
    _take(_ROE_MIN, text, payload, "roe_min", percent=True)
    _take(_ROE_MAX, text, payload, "roe_max", percent=True)
    _take(_PE_MIN, text, payload, "pe_min", percent=False)
    _take(_PE_MAX, text, payload, "pe_max", percent=False)
    _take(_GROWTH_MIN, text, payload, "revenue_growth_min", percent=True)
    _take(_GROWTH_MAX, text, payload, "revenue_growth_max", percent=True)
    _take(_MCAP_MIN, text, payload, "market_cap_min", percent=False, money=True)
    _take(_MCAP_MAX, text, payload, "market_cap_max", percent=False, money=True)
    _take(_DIV_MIN, text, payload, "dividend_yield_min", percent=True)
    _take(_MARGIN_MIN, text, payload, "profit_margin_min", percent=True)
    place = _place_search(text)
    if place is not None:
        payload["search"] = place
    if place is None and not any(name.endswith(("_min", "_max")) for name in payload):
        searchable = without_sector if sector is not None else text
        if asset_type is not None:
            searchable = _asset_match(searchable)[1]
        found = _leftover_search(searchable)
        if found is not None:
            payload["search"] = found
    return require_criteria(screen_from_mapping(payload))


def drop_unmentioned(query: str, parsed: ScreenRequest) -> ScreenRequest:
    """Keep a model filter only when the sentence itself names it."""
    text = _normalize(query)
    update: dict[str, Decimal | str | None] = {}
    sector, _rest = _sector_match(text)
    update["sector"] = sector
    asset_type, _asset_rest = _asset_match(text)
    update["asset_type"] = asset_type
    update["search"] = None
    if not re.search(r"\d", text):
        for name in (
            "roe",
            "pe",
            "revenue_growth",
            "market_cap",
            "eps",
            "revenue",
            "profit_margin",
            "dividend_yield",
            "beta",
            "ebitda",
            "price_to_book",
            "price_to_sales",
            "roa",
            "earnings_growth",
        ):
            update[f"{name}_min"] = None
            update[f"{name}_max"] = None
    if parsed.industry and parsed.industry not in text:
        update["industry"] = None
    if parsed.exchange and parsed.exchange not in text:
        update["exchange"] = None
    return require_criteria(parsed.model_copy(update=update))


_RATIO_FIELDS = frozenset(
    f"{name}_{bound}"
    for name in (
        "roe",
        "revenue_growth",
        "profit_margin",
        "dividend_yield",
        "roa",
        "earnings_growth",
    )
    for bound in ("min", "max")
)


def screen_from_model_json(
    data: object,
) -> ScreenRequest:  # filters object and returns strctured JSON
    """Accept only the screen schema. A `sql` key or other extra field fails."""
    if not isinstance(data, dict):
        raise AppError(
            "Language model did not return a filter object",
            status_code=422,
        )
    payload = {
        key: _coerce_model_value(key, value)
        for key, value in data.items()
        if key not in {"limit", "offset", "sort_by", "sort_direction"}
    }
    return require_criteria(screen_from_mapping(payload))


_IGNORED_LABELS = {"all", "any", "none", "null", "n/a", "na"}


def _coerce_model_value(key: str, value: object) -> object:
    """Turn a model percent into the decimal stored for that ratio."""
    if value is None or value == "":
        return None
    if key in {"sector", "industry", "exchange"} and isinstance(value, str):
        if value.strip().lower() in _IGNORED_LABELS:
            return None
    if key not in _RATIO_FIELDS:
        return value
    text = str(value).strip()
    marked_percent = text.endswith("%") or text.endswith("percent")
    numeric = text.removesuffix("%").removesuffix("percent").strip()
    try:
        number = Decimal(numeric)
    except Exception:
        return value
    if marked_percent or number > 1:
        return number / Decimal("100")
    return number


def screen_from_mapping(payload: object) -> ScreenRequest:
    try:
        # validate the payload against the schema
        return ScreenRequest.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            "That screen is not a filter Portfolytix will run",
            status_code=422,
        ) from exc


def require_criteria(
    parsed: ScreenRequest,
) -> ScreenRequest:  # check if the parsed object has any criteria
    criteria = tuple(getattr(parsed, name) for name in CRITERIA_FIELDS)
    if all(item is None for item in criteria):
        raise AppError(
            "Could not turn that into a structured screen",
            status_code=422,
        )
    return parsed


def _normalize(query: str) -> str:
    text = " ".join(query.lower().split())
    for wrong, right in _TYPOS:
        text = text.replace(wrong, right)
    if re.fullmatch(
        r"(?:(?:find|show|list|screen)\s+)?"
        r"(?:(?:me|all|the)\s+)*"
        r"tech(?:\s+(?:companies|company|stocks|stock|securities|shares))?",
        text,
    ):
        text = re.sub(r"\btech\b", "technology", text)
    return text


def _sector_match(text: str) -> tuple[str | None, str]:
    for phrase, sector in _SECTORS:
        if phrase in text:
            return sector, text.replace(phrase, " ", 1)
    return None, text


def _asset_match(text: str) -> tuple[str | None, str]:
    for pattern, kind in _ASSET_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            return kind, text[: match.start()] + " " + text[match.end() :]
    if re.fullmatch(
        r"(?:(?:find|show|list|screen)\s+)?(?:(?:me|all|the)\s+)*"
        r"index(?:\s+(?:companies|company|stocks|stock|securities))?",
        text,
    ):
        return "index", ""
    return None, text


def _place_search(text: str) -> str | None:
    """A place name is a name search, not a sector the model may invent."""
    if "hong kong" in text:
        return "hong kong"
    if re.search(r"\b(chinese|china)\b", text) and not re.search(
        r"\bex[- ]china\b", text
    ):
        return "china"
    return None


def _leftover_search(text: str) -> str | None:
    words = re.findall(r"[a-z0-9]+(?:['.&][a-z0-9]+)*", text)
    kept = [word for word in words if word not in _STOP and not word.isdigit()]
    if not kept or len(kept) > 4 or any(word in _SQL_WORDS for word in kept):
        return None
    if any(re.fullmatch(r"[a-z][a-z0-9.'&-]{0,40}", word) is None for word in kept):
        return None
    return " ".join(kept)


def _take(
    pattern: re.Pattern[str],
    text: str,
    payload: dict[str, Decimal | str],
    field: str,
    *,
    percent: bool,
    money: bool = False,
) -> None:
    match = pattern.search(text)  # search for the pattern in the text
    if match is None:
        return
    number = Decimal(match.group("n"))  # extract the number from the match
    unit = match.groupdict().get("unit")  # extract the unit from the match
    if percent:
        number = _as_ratio(number, unit)  # convert the number to a ratio
    elif money:
        number = _as_dollars(number, unit)  # convert the number to dollars
    payload[field] = number


def _as_ratio(number: Decimal, unit: str | None) -> Decimal:
    if unit or number > 1:
        return number / Decimal("100")
    return number


def _as_dollars(number: Decimal, unit: str | None) -> Decimal:
    if unit in {"billion", "bn"}:
        return number * Decimal("1000000000")
    if unit in {"million", "mm"}:
        return number * Decimal("1000000")
    return number
