"""Read the text of one Yahoo Finance story page. The article is not stored."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlsplit

import httpx

from app.market_data.errors import ProviderError

_ALLOWED_HOSTS = {"finance.yahoo.com"}
_SKIP = (
    "stock advisor",
    "double down",
    "see the 3 stocks",
    "no position in any of the stocks",
)
_TEXT_LIMIT = 2400


def fetch_article_text(url: str, client: httpx.Client | None = None) -> str:
    """Paragraphs from a Yahoo Finance story. Other hosts are refused."""
    if urlsplit(url.strip()).hostname not in _ALLOWED_HOSTS:
        raise ProviderError(
            "News summary only reads Yahoo Finance story pages",
            retryable=False,
        )
    if not url.strip().startswith("https://"):
        raise ProviderError(
            "News summary only reads Yahoo Finance story pages",
            retryable=False,
        )
    owns_client = client is None
    http = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        response = http.get(url, headers={"User-Agent": "Portfolytix/1.0"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError("The story page could not be read") from exc
    finally:
        if owns_client:
            http.close()
    if urlsplit(str(response.url)).hostname not in _ALLOWED_HOSTS:
        raise ProviderError("The story page left Yahoo Finance", retryable=False)
    return article_text(response.text)


def article_text(html: str) -> str:
    """Keep story paragraphs and drop short lines and subscription prompts."""
    chunks: list[str] = []
    total = 0
    for raw in re.findall(r"<p\b[^>]*>(.*?)</p>", html, flags=re.I | re.S):
        text = unescape(re.sub(r"<[^>]+>", " ", raw))
        text = " ".join(text.split())
        if len(text) < 80:
            continue
        lowered = text.lower()
        if any(phrase in lowered for phrase in _SKIP):
            continue
        chunks.append(text)
        total += len(text)
        if total >= _TEXT_LIMIT:
            break
    return "\n".join(chunks)[:_TEXT_LIMIT]
