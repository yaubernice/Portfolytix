"use client";

import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import NewsList, { storyScope } from "../../components/NewsList";
import { usePortfolio } from "../../components/usePortfolio";
import { EmptyState, ErrorState, Skeleton } from "../../components/UI";
import { api } from "../../lib/api";

const FILTERS = [
  ["holdings", "Holdings"],
  ["watchlist", "Watchlist"],
  ["market", "Broader market"],
];

function storyKey(item) {
  const headline = String(item.headline || "").toLowerCase().replace(/\s+/g, " ").trim();
  const url = String(item.url || "").trim();
  return url || headline;
}

function hasHeadline(item) {
  const headline = String(item.headline || "").trim();
  return headline.length > 3 && !/^no headline/i.test(headline);
}

function headlineWords(value) {
  return new Set(String(value || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((word) => word.length > 3));
}

function nearDuplicate(left, right) {
  const a = headlineWords(left.headline);
  const b = headlineWords(right.headline);
  if (a.size < 4 || b.size < 4) return false;
  let shared = 0;
  for (const word of a) if (b.has(word)) shared += 1;
  return shared / Math.min(a.size, b.size) >= 0.75;
}

function dedupe(items) {
  const seen = new Set();
  const rows = [];
  for (const item of items) {
    if (!hasHeadline(item)) continue;
    const key = storyKey(item);
    if (!key || seen.has(key)) continue;
    if (rows.some((row) => nearDuplicate(row, item))) continue;
    seen.add(key);
    rows.push(item);
  }
  return rows;
}

export default function NewsPage() {
  const { portfolios, portfolioId, ready, error: portfolioError } = usePortfolio();
  const [news, setNews] = useState(null);
  const [held, setHeld] = useState([]);
  const [watched, setWatched] = useState([]);
  const [filter, setFilter] = useState("holdings");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return undefined;
    if (!portfolioId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    async function load() {
      try {
        const [portfolioNews, positionBody, watchPage] = await Promise.all([
          api(`/portfolios/${portfolioId}/news`),
          api(`/portfolios/${portfolioId}/positions`).catch(() => null),
          api("/watchlists?limit=20").catch(() => ({ items: [] })),
        ]);
        const holdingTickers = (positionBody?.positions || [])
          .filter((row) => Number(row.quantity) > 0 && row.ticker)
          .map((row) => row.ticker.toUpperCase());
        const details = await Promise.all(
          (watchPage.items || []).slice(0, 5).map((list) => api(`/watchlists/${list.id}?limit=50`).catch(() => null)),
        );
        const watchTickers = [];
        for (const detail of details) {
          for (const item of detail?.items || []) {
            const ticker = String(item.ticker || "").toUpperCase();
            if (ticker && !watchTickers.includes(ticker)) watchTickers.push(ticker);
          }
        }
        const extra = watchTickers.filter((ticker) => !holdingTickers.includes(ticker)).slice(0, 4);
        const extraNews = await Promise.all(
          extra.map((ticker) => api(`/news?ticker=${encodeURIComponent(ticker)}`).catch(() => null)),
        );
        const items = dedupe([
          ...(portfolioNews.items || []),
          ...extraNews.flatMap((body) => body?.items || []),
        ]);
        if (cancelled) return;
        setHeld(holdingTickers);
        setWatched(watchTickers);
        setNews({ ...portfolioNews, items });
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [portfolioId, ready]);

  const visible = (news?.items || []).filter((item) => storyScope(item, held, watched) === filter);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Reading</p>
            <h1>News</h1>
            <p className="muted">Headlines for this portfolio and the symbols you watch. The line under a headline is the stored story text when the provider sent one. If none was stored, the line says so. Opening a story reads that article. The publisher&apos;s article stays separate.</p>
          </div>
        </header>
        <ErrorState message={error || portfolioError} />
        {loading ? <Skeleton lines={6} label="Loading news" /> : null}
        {!loading && ready && !portfolios.length ? <EmptyState title="No portfolios">Create a portfolio and add a buy before news can follow those stocks.</EmptyState> : null}
        {!loading && news ? (
          <section aria-labelledby="news-title">
            <div className="block-head">
              <h2 id="news-title">Stories</h2>
              <p className="muted">{news.note}</p>
            </div>
            <div className="filter-tabs" role="group" aria-label="Story scope">
              {FILTERS.map(([id, label]) => (
                <button key={id} type="button" aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>
              ))}
            </div>
            {news.unavailable?.length && filter === "holdings" ? <p className="compact-note">No headline for {news.unavailable.join(", ")}.</p> : null}
            {visible.length ? (
              <NewsList items={visible} provider={news.provider} held={held} watched={watched} />
            ) : (
              <EmptyState title="Nothing in this view">
                {filter === "holdings" ? "No headline names an open holding. A related ticker is not treated as the subject." : null}
                {filter === "watchlist" ? "Add a symbol to a watchlist, or none of these stories name one." : null}
                {filter === "market" ? "These stories stay inside your holdings and watchlist. Nothing here names a company outside that set." : null}
              </EmptyState>
            )}
          </section>
        ) : null}
      </main>
    </>
  );
}
