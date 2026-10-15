from datetime import date

import pytest

from app.market_data.calendar import bar_is_stale, easter_sunday, sessions_since
from app.market_data.errors import ProviderError
from app.quotes.factory import build_news_source, build_quote_source


def test_easter_and_a_holiday_do_not_count_as_a_missing_session() -> None:
    assert easter_sunday(2026) == date(2026, 4, 5)
    # Wednesday before Thanksgiving 2025, checked the Friday after.
    assert sessions_since(date(2025, 11, 26), date(2025, 11, 28)) == 1
    assert bar_is_stale(
        date(2025, 11, 26),
        date(2025, 11, 28),
        after_business_days=3,
    ) is False


def test_weekend_gap_is_not_stale_and_a_long_gap_is() -> None:
    assert sessions_since(date(2026, 10, 9), date(2026, 10, 12)) == 1
    assert bar_is_stale(
        date(2026, 10, 9),
        date(2026, 10, 12),
        after_business_days=3,
    ) is False
    assert bar_is_stale(
        date(2024, 1, 2),
        date(2026, 10, 15),
        after_business_days=3,
    ) is True


def test_unknown_quote_and_news_providers_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.quotes.factory.settings.quote_provider", "mystery")
    with pytest.raises(ProviderError, match="QUOTE_PROVIDER"):
        build_quote_source()
    monkeypatch.setattr("app.quotes.factory.settings.news_provider", "mystery")
    monkeypatch.setattr("app.quotes.factory.settings.quote_provider", "simulator")
    with pytest.raises(ProviderError, match="NEWS_PROVIDER"):
        build_news_source()
