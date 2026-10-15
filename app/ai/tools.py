from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.core.exceptions import AppError, NotFoundError
from app.quotes.store import QuoteStore
from app.schemas.screening import ScreenRequest
from app.services.analytics_service import AnalyticsService
from app.services.reference_service import ReferenceService
from app.services.screening_service import ScreeningService

_DANGEROUS_FIELDS = {"sql", "query", "raw_sql", "database_query"}


class SafeOperation(StrEnum):
    PORTFOLIO_ANALYTICS = "portfolio_analytics"
    SCREEN_SECURITIES = "screen_securities"
    CURRENT_QUOTE = "current_quote"
    SECURITY_FUNDAMENTALS = "security_fundamentals"
    RECENT_NEWS = "recent_news"


class _ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortfolioAnalyticsCall(_ToolCall):
    name: Literal[SafeOperation.PORTFOLIO_ANALYTICS]
    portfolio_id: UUID


class ScreenSecuritiesCall(_ToolCall):
    name: Literal[SafeOperation.SCREEN_SECURITIES]
    screen: ScreenRequest


class CurrentQuoteCall(_ToolCall):
    name: Literal[SafeOperation.CURRENT_QUOTE]
    ticker: str = Field(min_length=1, max_length=16)


class SecurityFundamentalsCall(_ToolCall):
    name: Literal[SafeOperation.SECURITY_FUNDAMENTALS]
    ticker: str = Field(min_length=1, max_length=16)


class RecentNewsCall(_ToolCall):
    name: Literal[SafeOperation.RECENT_NEWS]
    ticker: str = Field(min_length=1, max_length=16)


ToolCall = Annotated[
    PortfolioAnalyticsCall
    | ScreenSecuritiesCall
    | CurrentQuoteCall
    | SecurityFundamentalsCall
    | RecentNewsCall,
    Field(discriminator="name"),
]
_TOOL_CALL_ADAPTER = TypeAdapter(ToolCall)


def validate_tool_call(value: object) -> ToolCall:
    """Reject arbitrary tools and database-shaped fields before execution."""
    if _contains_dangerous_field(value):
        raise AppError("Tool call contains a forbidden field", status_code=422)
    try:
        return _TOOL_CALL_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise AppError(
            "Unknown or invalid assistant operation",
            status_code=422,
        ) from exc


class SafeToolExecutor:
    """Execute a fixed application-service allowlist, never model-authored SQL."""

    def __init__(
        self,
        *,
        analytics: AnalyticsService,
        screening: ScreeningService,
        reference: ReferenceService,
        quotes: QuoteStore,
    ) -> None:
        self.analytics = analytics
        self.screening = screening
        self.reference = reference
        self.quotes = quotes

    def execute(self, call: ToolCall) -> dict:
        if isinstance(call, PortfolioAnalyticsCall):
            # AnalyticsService enforces portfolio ownership.
            analytics = self.analytics.get_analytics(call.portfolio_id)
            return analytics.model_dump(mode="json")
        if isinstance(call, ScreenSecuritiesCall):
            return self.screening.screen(call.screen).model_dump(mode="json")
        if isinstance(call, CurrentQuoteCall):
            rows = self.quotes.snapshot([call.ticker.strip().upper()])
            if not rows:
                raise NotFoundError(
                    f"Current quote for {call.ticker.upper()} not found"
                )
            return rows[0].model_dump(mode="json")
        if isinstance(call, SecurityFundamentalsCall):
            profile = self.reference.profile(call.ticker)
            return profile.model_dump(
                mode="json",
                exclude={
                    "prices",
                    "latest_close",
                    "latest_close_at",
                    "history_source",
                    "history_updated_at",
                    "history_timeliness",
                },
            )
        if isinstance(call, RecentNewsCall):
            return self.reference.news(call.ticker).model_dump(mode="json")
        raise AppError("Unknown assistant operation", status_code=422)


def _contains_dangerous_field(value: object) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in _DANGEROUS_FIELDS for key in value):
            return True
        return any(_contains_dangerous_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_dangerous_field(item) for item in value)
    return False
