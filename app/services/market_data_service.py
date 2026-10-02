from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.market_data.errors import ProviderError
from app.market_data.normalize import normalize_bar
from app.market_data.provider import MarketDataProvider
from app.market_data.types import NormalizedBar
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
    results: list[TickerIngestResult] = field(default_factory=list)

    @property
    def failed_tickers(self) -> list[str]: #list of tickers that failed to ingest
        return [row.ticker for row in self.results if row.error]


class MarketDataService:
    """Fetch → validate → upsert. One ticker failure does not abort the rest."""

    def __init__(self, session: Session, provider: MarketDataProvider) -> None:
        self.session = session
        self.provider = provider
        self.securities = SecurityRepository(session)
        self.prices = PriceRepository(session)

    def ingest(
        self,
        tickers: list[str],
        start: date,
        end: date,
    ) -> IngestReport:
        report = IngestReport(provider=self.provider.name, start=start, end=end)
        for raw_ticker in tickers: 
            ticker = raw_ticker.upper()
            # uppercase so it matches securities.ticker
            result = self._ingest_one(ticker, start, end) #ingest one ticker
            report.results.append(result)
            if result.error: #if the ticker failed to ingest, log a warning
                logger.warning(
                    "ingest_ticker_failed",
                    extra={"ticker": ticker, "error": result.error},
                )
            else:
                logger.info(
                    "ingest_ticker_ok",
                    extra={
                        "ticker": ticker,
                        "fetched": result.fetched,
                        "accepted": result.accepted,
                        "upserted": result.upserted,
                        "skipped_invalid": result.skipped_invalid,
                    },
                )
        return report

    def _ingest_one(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> TickerIngestResult:
        result = TickerIngestResult(ticker=ticker)
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            result.error = "unknown_ticker"
            return result
        try:
            raw_bars = self.provider.fetch_daily_bars(ticker, start, end)
        except ProviderError as exc: #API unavailable, rate limit exceeded, etc.
            result.error = str(exc)
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
                    extra={"ticker": ticker, "day": str(raw.day), "reason": reason},
                )
                continue
            accepted.append(bar) #add the normalized bar to the list of accepted bars
        result.accepted = len(accepted)
        # upsert the accepted bars into the database
        result.upserted = self.prices.upsert_bars(security.id, accepted)
        return result
