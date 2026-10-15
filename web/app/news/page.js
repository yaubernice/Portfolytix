"use client";

import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import NewsList from "../../components/NewsList";
import { EmptyState, ErrorState, Skeleton } from "../../components/UI";
import { api } from "../../lib/api";

export default function NewsPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [news, setNews] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/portfolios")
      .then((rows) => {
        setPortfolios(rows);
        if (rows[0]) setPortfolioId(rows[0].id);
        else setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!portfolioId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    api(`/portfolios/${portfolioId}/news`)
      .then((body) => {
        if (!cancelled) setNews(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [portfolioId]);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Holdings</p>
            <h1>News</h1>
            <p className="muted">Latest headlines for stocks in the selected portfolio, with a photo when the provider sends one.</p>
          </div>
          {portfolios.length ? (
            <label className="field">
              Portfolio
              <select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>
                {portfolios.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
              </select>
            </label>
          ) : null}
        </header>
        {error ? <ErrorState title="News could not be loaded">{error}</ErrorState> : null}
        {loading ? <Skeleton lines={6} label="Loading news" /> : null}
        {!loading && !error && !portfolios.length ? <EmptyState title="No portfolios">Create a portfolio and add a buy before news can follow those stocks.</EmptyState> : null}
        {!loading && !error && news ? (
          <section className="panel" aria-labelledby="news-title">
            <div className="panel-header">
              <div>
                <h2 id="news-title">Latest headlines</h2>
                <p className="muted">{news.note} Provider: {news.provider || "none"}.</p>
              </div>
            </div>
            {news.unavailable?.length ? <p className="metadata">No headline for {news.unavailable.join(", ")}.</p> : null}
            {news.items?.length ? <NewsList items={news.items} provider={news.provider} /> : <EmptyState title="No headlines">The news provider returned nothing for these open positions.</EmptyState>}
          </section>
        ) : null}
      </main>
    </>
  );
}
