"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ExplainPoints } from "../../../components/ExplainLayer";
import Nav from "../../../components/Nav";
import { ErrorState, Skeleton } from "../../../components/UI";
import { api } from "../../../lib/api";

export default function LearnArticle() {
  const params = useParams();
  const search = useSearchParams();
  const slug = params.slug;
  const ticker = search.get("ticker") || "";
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/portfolios")
      .then((rows) => {
        setPortfolios(rows);
        if (rows[0]) setPortfolioId(rows[0].id);
      })
      .catch((err) => setError(err.message))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!slug || !ready) return undefined;
    let cancelled = false;
    const query = new URLSearchParams();
    if (portfolioId) query.set("portfolio_id", portfolioId);
    if (ticker) query.set("ticker", ticker);
    const suffix = query.toString() ? `?${query}` : "";
    setLoading(true);
    api(`/learn/${slug}${suffix}`)
      .then((body) => {
        if (!cancelled) {
          setPage(body);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setPage(null);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, portfolioId, ticker, ready]);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Learning</p>
            <h1>{page?.title || "Term"}</h1>
            <p className="muted"><Link href="/learn">All terms</Link></p>
          </div>
          <label className="field">Portfolio
            <select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>
              {portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        </header>
        <ErrorState message={error} />
        {loading ? <Skeleton lines={6} label="Loading explanation" /> : null}
        {page ? (
          <section className="panel learn-section">
            <ExplainPoints page={page} />
            <p className="muted">{page.disclaimer}</p>
          </section>
        ) : null}
      </main>
    </>
  );
}
