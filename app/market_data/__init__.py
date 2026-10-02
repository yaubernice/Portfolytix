"""Vendor adapters for daily OHLCV. Ingest does not import a specific API."""

from app.market_data.factory import build_provider
from app.market_data.provider import MarketDataProvider

__all__ = ["MarketDataProvider", "build_provider"]
