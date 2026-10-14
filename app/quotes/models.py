from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.config import settings
from app.schemas.common import DecimalStr, OptionalDecimalStr


class LiveQuote(BaseModel):
    """Latest price for one symbol. This is current state, not tick history."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    price: DecimalStr
    bid: OptionalDecimalStr = None
    ask: OptionalDecimalStr = None
    volume: int | None = None
    # ``timestamp`` remains for API compatibility; it is the provider event time.
    timestamp: datetime
    provider_timestamp: datetime | None = None
    received_at: datetime | None = None
    age_seconds: float = 0.0
    source: str
    previous_close: OptionalDecimalStr = None
    change: OptionalDecimalStr = None
    change_percent: OptionalDecimalStr = None
    # realtime, delayed, stale, or simulated. Missing rows are unavailable.
    timeliness: str = "delayed"
    provider_timeliness: str | None = None
    is_stale: bool = False

    @model_validator(mode="after")
    def fill_freshness_times(self) -> LiveQuote:
        if self.provider_timestamp is None:
            self.provider_timestamp = self.timestamp
        if self.received_at is None:
            self.received_at = datetime.now(UTC)
        if self.provider_timeliness is None:
            self.provider_timeliness = self.timeliness
        return self

    def freshened(
        self,
        *,
        now: datetime | None = None,
        max_age_seconds: float | None = None,
    ) -> LiveQuote:
        """Return the quote with age and stale semantics evaluated now."""
        current = now or datetime.now(UTC)
        provider_time = self.provider_timestamp or self.timestamp
        if provider_time.tzinfo is None:
            provider_time = provider_time.replace(tzinfo=UTC)
        age = max(0.0, (current - provider_time).total_seconds())
        threshold = (
            settings.quote_stale_after_seconds
            if max_age_seconds is None
            else max_age_seconds
        )
        original = self.provider_timeliness or self.timeliness
        stale = age > threshold
        # Preserve the provider's original label separately, but never present
        # an old quote as current regardless of whether it began delayed,
        # simulated, or realtime.
        timeliness = "stale" if stale else original
        return self.model_copy(
            update={
                "provider_timestamp": provider_time,
                "age_seconds": round(age, 3),
                "provider_timeliness": original,
                "timeliness": timeliness,
                "is_stale": stale,
            }
        )


def with_change(quote: LiveQuote) -> LiveQuote:
    """Fill change from previous_close when the vendor did not send it."""
    if quote.previous_close is None or quote.previous_close == 0:
        return quote
    if quote.change is not None and quote.change_percent is not None:
        return quote
    change = quote.price - quote.previous_close
    return quote.model_copy(
        update={
            "change": change,
            "change_percent": change / quote.previous_close,
        }
    )


def quote_from_parts(
    *,
    ticker: str,
    price: Decimal,
    timestamp: datetime,
    source: str,
    bid: Decimal | None = None,
    ask: Decimal | None = None,
    volume: int | None = None,
    previous_close: Decimal | None = None,
    timeliness: str = "delayed",
    received_at: datetime | None = None,
) -> LiveQuote:
    return with_change(
        LiveQuote(
            ticker=ticker.upper(),
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            timestamp=timestamp,
            provider_timestamp=timestamp,
            received_at=received_at or datetime.now(UTC),
            source=source,
            previous_close=previous_close,
            timeliness=timeliness,
            provider_timeliness=timeliness,
        )
    )
