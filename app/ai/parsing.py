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
    ("technology", "technology"),
    ("healthcare", "healthcare"),
    ("financials", "financials"),
    ("industrials", "industrials"),
    ("energy", "energy"),
)

_MIN_WORD = (
    r"(?:above|over|greater than|more than|higher than|at least|>=|>)"
)
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


def parse_screen_text(query: str) -> ScreenRequest: #filters object
    """Map a narrow English pattern onto ScreenRequest. No SQL is built."""
    text = " ".join(query.lower().split())
    payload: dict[str, Decimal | str] = {}
    for phrase, sector in _SECTORS:
        if phrase in text:
            payload["sector"] = sector
            break
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
    return require_criteria(screen_from_mapping(payload))


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
            "That screen is not a filter FinSight will run",
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


def _take(
    pattern: re.Pattern[str],
    text: str,
    payload: dict[str, Decimal | str],
    field: str,
    *,
    percent: bool,
    money: bool = False,
) -> None:
    match = pattern.search(text) #search for the pattern in the text
    if match is None:
        return
    number = Decimal(match.group("n")) #extract the number from the match
    unit = match.groupdict().get("unit") #extract the unit from the match
    if percent:
        number = _as_ratio(number, unit) #convert the number to a ratio
    elif money:
        number = _as_dollars(number, unit) #convert the number to dollars
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
