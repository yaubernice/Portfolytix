"""Headline cache records. Article bodies are not stored."""

from __future__ import annotations

SUMMARY_LIMIT = 500


def news_record(
    *,
    headline: str,
    source: str,
    url: str,
    published_at: str,
    tickers: list[str],
    summary: str,
    sentiment: str | None,
    provider: str,
    image_url: str = "",
) -> dict:
    symbols: list[str] = []
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    text = " ".join(summary.split())
    if len(text) > SUMMARY_LIMIT:
        text = text[: SUMMARY_LIMIT - 1].rstrip() + "…"
    label = sentiment.strip() if isinstance(sentiment, str) else ""
    picture = image_url.strip()
    if not picture.startswith(("https://", "http://")) or len(picture) > 1000:
        picture = ""
    return {
        "headline": headline.strip(),
        "summary": text,
        "source": source,
        "url": url,
        "published_at": published_at,
        "tickers": symbols,
        "sentiment": label or None,
        "provider": provider,
        "image_url": picture,
    }
