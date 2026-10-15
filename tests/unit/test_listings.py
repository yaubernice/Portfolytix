from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Security
from app.market_data.listings import (
    apply_listings,
    merge_listings,
    parse_nasdaq_listed,
    parse_other_listed,
)
from app.market_data.yahoo_news import parse_yahoo_news

NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
    "Round Lot Size|ETF|NextShares\n"
    "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
    "ZZZT|Test Issue|Q|Y|N|100|N|N\n"
    "QQQ|Invesco QQQ Trust|G|N|N|100|Y|N\n"
    "File Creation Time: 1015202608:16|||||||\n"
)

OTHER = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
    "Test Issue|NASDAQ Symbol\n"
    "JPM|JPMorgan Chase & Co. Common Stock|N|JPM|N|100|N|JPM\n"
    "AAPL|Apple Elsewhere|N|AAPL|N|100|N|AAPL\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
    "TEST|Skip Me|N|TEST|N|100|Y|TEST\n"
    "File Creation Time: 1015202608:16||||||\n"
)


def test_listing_files_skip_tests_and_keep_the_first_ticker() -> None:
    rows = merge_listings(parse_nasdaq_listed(NASDAQ), parse_other_listed(OTHER))
    by_ticker = {row.ticker: row for row in rows}
    assert set(by_ticker) == {"AAPL", "QQQ", "JPM", "SPY"}
    assert by_ticker["AAPL"].exchange == "NASDAQ"
    assert by_ticker["AAPL"].name == "Apple Inc. - Common Stock"
    assert by_ticker["QQQ"].asset_type == "etf"
    assert by_ticker["JPM"].exchange == "NYSE"
    assert by_ticker["JPM"].mic == "XNYS"
    assert by_ticker["SPY"].exchange == "NYSE Arca"
    assert by_ticker["SPY"].asset_type == "etf"


def test_apply_listings_keeps_existing_rows_and_retires_bench(
    sqlite_session: Session,
) -> None:
    sqlite_session.add(
        Security(
            ticker="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            sector="Technology",
            currency="USD",
            provider="seed",
            provider_symbol="AAPL",
        )
    )
    sqlite_session.add(
        Security(
            ticker="BENCH00000000001",
            name="Placeholder",
            exchange="NASDAQ",
            sector="Financials",
            currency="USD",
            provider="seed",
            provider_symbol="BENCH00000000001",
        )
    )
    sqlite_session.flush()
    added, retired = apply_listings(
        sqlite_session,
        merge_listings(parse_nasdaq_listed(NASDAQ), parse_other_listed(OTHER)),
    )
    assert added == 3
    assert retired == 1
    apple = sqlite_session.scalar(select(Security).where(Security.ticker == "AAPL"))
    assert apple is not None
    assert apple.name == "Apple Inc."
    assert apple.sector == "Technology"
    bench = sqlite_session.scalar(
        select(Security).where(Security.ticker == "BENCH00000000001")
    )
    assert bench is not None
    assert bench.is_active is False
    jpm = sqlite_session.scalar(select(Security).where(Security.ticker == "JPM"))
    assert jpm is not None
    assert jpm.provider == "nasdaq"
    assert jpm.sector == ""
    assert jpm.country == "US"


def test_yahoo_news_keeps_a_photo_and_does_not_invent_a_summary() -> None:
    items = parse_yahoo_news(
        {
            "news": [
                {
                    "title": "Apple updates guidance",
                    "publisher": "Reuters",
                    "link": "https://example.test/a",
                    "providerPublishTime": 1_700_000_000,
                    "type": "STORY",
                    "relatedTickers": ["AAPL", "MSFT"],
                    "thumbnail": {
                        "resolutions": [
                            {
                                "url": "https://example.test/photo.jpg",
                                "width": 1200,
                                "tag": "original",
                            }
                        ]
                    },
                },
                {
                    "title": "Unrelated bank note",
                    "publisher": "Example",
                    "link": "https://example.test/b",
                    "providerPublishTime": 1_700_000_100,
                    "type": "STORY",
                    "relatedTickers": ["JPM"],
                },
            ]
        },
        "AAPL",
    )
    assert len(items) == 1
    assert items[0]["summary"] == ""
    assert items[0]["image_url"] == "https://example.test/photo.jpg"
    assert items[0]["tickers"] == ["AAPL", "MSFT"]
    assert items[0]["provider"] == "yahoo"
