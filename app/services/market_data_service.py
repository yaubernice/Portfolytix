from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.db.models import Security
from app.market_data.errors import ProviderError
from app.market_data.normalize import normalize_bar
from app.market_data.provider import MarketDataProvider
from app.market_data.types import NormalizedBar, RawBar
from app.repositories.price_repository import PriceRepository
from app.repositories.security_repository import SecurityRepository

logger = logging.getLogger(__name__)


@dataclass
class TickerIngestResult: #result of ingesting one ticker
    ticker: str
    fetched: int = 0
    accepted: int = 0
    upserted: int = 0
    skipped_invalid: int = 0
    error: str | None = None


@dataclass
class IngestReport: #report of ingesting all tickers
    provider: str
    start: date
    end: date
    symbols_requested: int = 0
    symbols_omitted: int = 0
    results: list[TickerIngestResult] = field(default_factory=list)

    @property
    def failed_tickers(self) -> list[str]: #list of tickers that failed to ingest
        return [row.ticker for row in self.results if row.error]


@dataclass
class _Symbol:
    label: str
    security: Security | None = None
    error: str | None = None


class MarketDataService:
    """Fetch → validate → upsert. One ticker failure does not abort the rest."""

    def __init__(
        self,
        session: Session,
        provider: MarketDataProvider,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.securities = SecurityRepository(session)
        self.prices = PriceRepository(session)
        self._sleep = sleep or time.sleep

    def ingest(
        self,
        tickers: list[str] | None,
        start: date,
        end: date,
        *,
        security_ids: list[UUID] | None = None,
        exchange: str | None = None,
        country: str | None = None,
        max_securities: int | None = None,
        max_window_days: int | None = None,
        max_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
        pause_seconds: float | None = None,
    ) -> IngestReport:
        window_days = (
            settings.market_data_max_window_days
            if max_window_days is None
            else max_window_days
        )
        _require_window(start, end, window_days)
        cap = (
            settings.market_data_max_securities
            if max_securities is None
            else max_securities
        )
        if cap < 1:
            raise ValueError("market_data_max_securities must be >= 1")
        attempts = (
            settings.market_data_max_attempts if max_attempts is None else max_attempts
        )
        backoff = (
            settings.market_data_retry_backoff_seconds
            if retry_backoff_seconds is None
            else retry_backoff_seconds
        )
        pause = (
            settings.market_data_pause_seconds
            if pause_seconds is None
            else pause_seconds
        )
        chosen, requested, omitted = self._select(
            tickers,
            security_ids=security_ids,
            exchange=exchange,
            country=country,
            cap=cap,
        )
        report = IngestReport(
            provider=self.provider.name,
            start=start,
            end=end,
            symbols_requested=requested,
            symbols_omitted=omitted,
        )
        for index, symbol in enumerate(chosen):
            if index and pause > 0:
                self._sleep(pause)
            result = self._ingest_one(
                symbol,
                start,
                end,
                attempts=max(attempts, 1),
                backoff=backoff,
            )
            report.results.append(result)
            if result.error: #if the ticker failed to ingest, log a warning
                logger.warning(
                    "ingest_ticker_failed",
                    extra={"ticker": result.ticker, "error": result.error},
                )
            else:
                logger.info(
                    "ingest_ticker_ok",
                    extra={
                        "ticker": result.ticker,
                        "fetched": result.fetched,
                        "accepted": result.accepted,
                        "upserted": result.upserted,
                        "skipped_invalid": result.skipped_invalid,
                    },
                )
        return report

    def _select(
        self,
        tickers: list[str] | None,
        *,
        security_ids: list[UUID] | None,
        exchange: str | None,
        country: str | None,
        cap: int,
    ) -> tuple[list[_Symbol], int, int]:
        if security_ids:
            symbols = [self._symbol_from_id(item, exchange) for item in security_ids]
        elif tickers is not None:
            symbols = [_Symbol(label=ticker.strip().upper()) for ticker in tickers]
        elif exchange or country:
            rows, total = self.securities.list_for_ingest(
                exchange=exchange,
                country=country,
                limit=cap,
            )
            symbols = [_Symbol(label=row.ticker, security=row) for row in rows]
            return symbols, total, max(total - len(symbols), 0)
        else:
            symbols = []
        requested = len(symbols)
        omitted = max(requested - cap, 0)
        return symbols[:cap], requested, omitted

    def _symbol_from_id(self, security_id: UUID, exchange: str | None) -> _Symbol:
        security = self.securities.get_by_id(security_id)
        if security is None:
            return _Symbol(label=str(security_id), error="unknown_security")
        if exchange and security.exchange.lower() != exchange.strip().lower():
            return _Symbol(
                label=security.ticker,
                security=security,
                error="exchange_mismatch",
            )
        return _Symbol(label=security.ticker, security=security)

    def _ingest_one(
        self,
        symbol: _Symbol,
        start: date,
        end: date,
        *,
        attempts: int,
        backoff: float,
    ) -> TickerIngestResult:
        result = TickerIngestResult(ticker=symbol.label)
        if symbol.error:
            result.error = symbol.error
            return result
        security = symbol.security
        if security is None:
            try:
                security = self.securities.get_by_ticker(symbol.label)
            except ConflictError as exc:
                result.error = str(exc)
                return result
            if security is None:
                result.error = "unknown_ticker"
                return result
        try:
            raw_bars = self._fetch(security.ticker, start, end, attempts, backoff)
        except ProviderError as exc: #API unavailable, rate limit exceeded, etc.
            result.error = str(exc)
            logger.warning(
                "ingest_symbol_failed",
                extra={"ticker": security.ticker, "error": result.error},
            )
            return result
        result.fetched = len(raw_bars)
        accepted: list[NormalizedBar] = []
        # bars that passed validation rules
        for raw in raw_bars:
            bar, reason = normalize_bar(raw)
            if bar is None:
                result.skipped_invalid += 1
                logger.info(
                    "ingest_bar_dropped",
                    extra={
                        "ticker": security.ticker,
                        "day": str(raw.day),
                        "reason": reason,
                    },
                )
                continue
            accepted.append(bar) #add the normalized bar to the list of accepted bars
        result.accepted = len(accepted)
        # upsert the accepted bars into the database
        result.upserted = self.prices.upsert_bars(
            security.id,
            accepted,
            source=self.provider.name,
        )
        if result.upserted:
            logger.info(
                "ingest_symbol_persisted",
                extra={
                    "ticker": security.ticker,
                    "fetched": result.fetched,
                    "upserted": result.upserted,
                },
            )
        elif result.fetched:
            logger.info(
                "ingest_symbol_unpersisted",
                extra={
                    "ticker": security.ticker,
                    "fetched": result.fetched,
                    "skipped_invalid": result.skipped_invalid,
                },
            )
        return result

    def _fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        attempts: int,
        backoff: float,
    ) -> list[RawBar]:
        last: ProviderError | None = None
        for attempt in range(attempts):
            try:
                return self.provider.fetch_daily_bars(ticker, start, end)
            except ProviderError as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= attempts:
                    break
                delay = backoff * (2**attempt)
                if delay > 0:
                    self._sleep(delay)
        assert last is not None
        raise last


def _require_window(start: date, end: date, max_days: int) -> None:
    if start > end:
        raise ValueError("ingest start must be on or before end")
    span = (end - start).days
    if span > max_days:
        raise ValueError(f"ingest window is {span} days; max is {max_days}")
