"""Yahoo quote summary for one listing. Incomplete snapshots are skipped."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import settings

YAHOO_CRUMB = "https://query1.finance.yahoo.com/v1/test/getcrumb"
YAHOO_SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_MODULES = "price,financialData,summaryDetail,assetProfile"


def parse_yahoo_snapshot(payload: dict) -> dict | None:
    """ROE, P/E, growth, and market cap. A missing figure drops the snapshot."""
    row = _summary_row(payload)
    if row is None:
        return None
    market_cap = _raw(row, "price", "marketCap")
    pe_ratio = _raw(row, "summaryDetail", "trailingPE")
    roe = _raw(row, "financialData", "returnOnEquity")
    revenue_growth = _raw(row, "financialData", "revenueGrowth")
    if (
        market_cap is None
        or market_cap <= 0
        or pe_ratio is None
        or roe is None
        or revenue_growth is None
    ):
        return None
    sector = (row.get("assetProfile") or {}).get("sector")
    label = sector.strip() if isinstance(sector, str) else ""
    return {
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "roe": roe,
        "revenue_growth": revenue_growth,
        "sector": label[:64],
    }


def parse_yahoo_quote(payload: dict) -> dict | None:
    """Latest Yahoo price. Market cap and P/E are included when Yahoo sends them."""
    row = _summary_row(payload)
    if row is None:
        return None
    price = _raw(row, "price", "regularMarketPrice")
    if price is None or price <= 0:
        return None
    market_cap = _raw(row, "price", "marketCap")
    if market_cap is not None and market_cap <= 0:
        market_cap = None
    quoted_at = None
    market_time = _raw(row, "price", "regularMarketTime")
    if market_time is not None and market_time > 0:
        quoted_at = datetime.fromtimestamp(int(market_time), UTC)
    return {
        "price": price,
        "market_cap": market_cap,
        "pe_ratio": _raw(row, "summaryDetail", "trailingPE"),
        "quoted_at": quoted_at,
    }


def fetch_snapshots(tickers: list[str]) -> dict[str, dict]:
    """One crumb, then each symbol. A failed symbol is omitted."""
    return _fetch(tickers, parse_yahoo_snapshot)


def parse_yahoo_chart_quote(payload: dict) -> dict | None:
    """Latest price from the chart feed. It does not include P/E or market cap."""
    result = (payload.get("chart") or {}).get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return None
    meta = result[0].get("meta") or {}
    price = _plain_number(meta.get("regularMarketPrice"))
    if price is None or price <= 0:
        return None
    quoted_at = None
    market_time = _plain_number(meta.get("regularMarketTime"))
    if market_time is not None and market_time > 0:
        quoted_at = datetime.fromtimestamp(int(market_time), UTC)
    return {
        "price": price,
        "market_cap": None,
        "pe_ratio": None,
        "previous_close": _plain_number(meta.get("chartPreviousClose")),
        "quoted_at": quoted_at,
    }


def fetch_latest_quotes(tickers: list[str]) -> dict[str, dict]:
    """Latest Yahoo chart price for each symbol. A failed symbol is omitted.

    Symbols are requested together, a few at a time, instead of one after another.
    """
    symbols: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        return {}
    workers = max(1, min(settings.provider_quote_workers, len(symbols)))
    found: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for symbol, parsed in pool.map(_chart_quote, symbols):
            if parsed is not None:
                found[symbol] = parsed
    return found


def _chart_quote(symbol: str) -> tuple[str, dict | None]:
    headers = {"User-Agent": "Portfolytix/1.0"}
    try:
        with httpx.Client(
            headers=headers, timeout=20.0, follow_redirects=True
        ) as client:
            response = client.get(
                YAHOO_CHART.format(symbol=symbol),
                params={"interval": "1d", "range": "5d"},
            )
    except httpx.HTTPError:
        return symbol, None
    if response.status_code != 200:
        return symbol, None
    try:
        return symbol, parse_yahoo_chart_quote(response.json())
    except ValueError:
        return symbol, None


def _fetch(tickers: list[str], parse) -> dict[str, dict]:
    symbols = []
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        return {}
    headers = {"User-Agent": "Portfolytix/1.0"}
    found: dict[str, dict] = {}
    try:
        with httpx.Client(
            headers=headers, timeout=20.0, follow_redirects=True
        ) as client:
            client.get("https://fc.yahoo.com")
            crumb_response = client.get(YAHOO_CRUMB)
            crumb = crumb_response.text.strip()
            if crumb_response.status_code != 200 or not crumb.isalnum():
                return {}
            for symbol in symbols:
                time.sleep(0.35)
                try:
                    response = client.get(
                        YAHOO_SUMMARY.format(symbol=symbol),
                        params={"modules": _MODULES, "crumb": crumb},
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code in (401, 429):
                    break
                if response.status_code != 200:
                    continue
                try:
                    parsed = parse(response.json())
                except ValueError:
                    continue
                if parsed is not None:
                    found[symbol] = parsed
    except httpx.HTTPError:
        return found
    return found


def _summary_row(payload: dict) -> dict | None:
    result = (payload.get("quoteSummary") or {}).get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return None
    return result[0]


def _plain_number(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number


def _raw(row: dict, block: str, key: str) -> Decimal | None:
    node = (row.get(block) or {}).get(key)
    value = node.get("raw") if isinstance(node, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number
