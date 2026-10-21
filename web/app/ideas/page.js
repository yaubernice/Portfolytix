"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { usePortfolio } from "../../components/usePortfolio";
import { EmptyState, ErrorState, money, number, percent, Skeleton, TickerIdentity } from "../../components/UI";
import { api } from "../../lib/api";

export default function IdeasPage() {
  const { portfolios, portfolioId, ready, error: portfolioError } = usePortfolio();
  const [recommendations, setRecommendations] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("ranked");

  useEffect(() => {
    if (!ready) return undefined;
    if (!portfolioId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    api(`/portfolios/${portfolioId}/recommendations`)
      .then((ideas) => {
        if (!cancelled) setRecommendations(ideas);
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
  }, [portfolioId, ready]);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Research</p>
            <h1>Companies to look at</h1>
            <p className="muted">A reason to look, not a recommendation to buy.</p>
          </div>
        </header>
        <ErrorState message={error || portfolioError} />
        {loading ? <Skeleton lines={6} label="Loading suggestions" /> : null}
        {!loading && ready && portfolios.length === 0 ? <EmptyState title="No portfolio yet">Create a portfolio before asking for ideas.</EmptyState> : null}
        {!loading && recommendations ? (
          <section aria-labelledby="ideas-title">
            <div className="block-head">
              <h2 id="ideas-title">Companies</h2>
              <div className="row">
                <label className="field">Search
                  <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ticker or name" />
                </label>
                <label className="field">Sort
                  <select value={sort} onChange={(event) => setSort(event.target.value)}>
                    <option value="ranked">Suggested order</option>
                    <option value="ticker">Ticker</option>
                    <option value="price">Latest price</option>
                    <option value="roe">ROE</option>
                    <option value="pe">P/E</option>
                  </select>
                </label>
              </div>
            </div>
            <p className="compact-note">{recommendations.disclaimer}</p>
            {recommendations.commentary ? <p className="compact-note">{recommendations.commentary_source === "llm" ? "Written by the configured model. " : "Restated from the stored figures. "}{recommendations.commentary}</p> : null}
            {recommendations.items.length === 0 ? <EmptyState title="No other companies yet">Stored figures are needed before a company can be suggested.</EmptyState> : (
              <ol className="idea-list">
                {recommendations.items
                  .filter((row) => {
                    const needle = query.trim().toLowerCase();
                    if (!needle) return true;
                    return `${row.ticker} ${row.name || ""}`.toLowerCase().includes(needle);
                  })
                  .sort((left, right) => {
                    const ranked = (a, b, direction) => {
                      const missingA = a == null || a === "";
                      const missingB = b == null || b === "";
                      if (missingA && missingB) return 0;
                      if (missingA) return 1;
                      if (missingB) return -1;
                      return direction * (Number(a) - Number(b));
                    };
                    if (sort === "ticker") return String(left.ticker).localeCompare(String(right.ticker));
                    if (sort === "price") return ranked(left.price, right.price, -1);
                    if (sort === "roe") return ranked(left.roe, right.roe, -1);
                    if (sort === "pe") return ranked(left.pe_ratio, right.pe_ratio, 1);
                    return 0;
                  })
                  .map((row) => (
                  <li className="idea-row" key={row.security_id}>
                    <Link className="ticker-link" href={`/securities/${row.ticker}`}>
                      <TickerIdentity ticker={row.ticker} name={row.name} />
                    </Link>
                    <p className="idea-sector">{row.sector || "Sector unavailable"}</p>
                    <dl className="idea-metrics">
                      <div><dt>Latest price</dt><dd>{row.price != null ? money(row.price) : "—"}</dd></div>
                      <div><dt><LearnTerm slug="roe">ROE</LearnTerm></dt><dd>{percent(row.roe)}</dd></div>
                      <div><dt><LearnTerm slug="pe-ratio">P/E</LearnTerm></dt><dd>{number(row.pe_ratio, { maximumFractionDigits: 2 })}</dd></div>
                    </dl>
                    <details className="idea-why">
                      <summary>Why look at it</summary>
                      {row.points?.length ? (
                        <ul className="idea-points">{row.points.map((point) => <li key={point}>{point}</li>)}</ul>
                      ) : <p>{row.reason}</p>}
                    </details>
                    <Link className="text-link" href={`/securities/${row.ticker}`}>Open {row.ticker}</Link>
                  </li>
                ))}
              </ol>
            )}
          </section>
        ) : null}
      </main>
    </>
  );
}
