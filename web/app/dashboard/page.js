"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, KpiCard, money, number, percent, Skeleton, StatusBadge, TimeSeriesChart, dateTime } from "../../components/UI";
import { useQuotes } from "../../components/useQuotes";
import { api } from "../../lib/api";

export default function DashboardPage() {
  const { quotes, status: quoteStatus } = useQuotes();
  const [email, setEmail] = useState("");
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [analytics, setAnalytics] = useState(null);
  const [positions, setPositions] = useState(null);
  const [system, setSystem] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/auth/me").then((user) => setEmail(user.email)).catch(() => setEmail(""));
    api("/portfolios").then((rows) => {
      setPortfolios(rows);
      if (rows[0]) setPortfolioId(rows[0].id);
      else setLoading(false);
    }).catch((err) => setError(err.message));
    Promise.all([api("/status"), api("/jobs?limit=5")])
      .then(([statusBody, jobsBody]) => {
        setSystem(statusBody);
        setJobs(jobsBody.items || []);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!portfolioId) return undefined;
    let cancelled = false;
    setError("");
    api(`/portfolios/${portfolioId}/analytics`)
      .then((body) => {
        if (!cancelled) setAnalytics(body);
      })
      .catch((err) => {
        if (!cancelled) {
          setAnalytics(null);
          setError(err.message);
        }
      });
    const loadPositions = () => {
      api(`/portfolios/${portfolioId}/positions`)
        .then((body) => {
          if (!cancelled) setPositions(body);
        })
        .catch(() => {
          if (!cancelled) setPositions(null);
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    loadPositions();
    const timer = setInterval(loadPositions, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [portfolioId]);

  useEffect(() => {
    if (portfolioId) sessionStorage.setItem("finsight_portfolio", portfolioId);
  }, [portfolioId]);

  const quoteRows = Object.values(quotes).sort((a, b) => a.ticker.localeCompare(b.ticker)).slice(0, 8);

  return (
    <>
      <Nav email={email} />
      <main id="main-content" className="content">
        <header className="page-header">
          <div><p className="eyebrow">Overview</p><h1>Dashboard</h1><p className="muted">Portfolio, market, and platform activity in one view.</p></div>
          <label className="field">Portfolio
            <select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>
              {portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        </header>
        <ErrorState message={error} />
        {loading && portfolioId ? <Skeleton lines={3} label="Loading dashboard" /> : null}
        {!loading && portfolios.length === 0 ? <EmptyState title="No portfolio found">Create a portfolio to populate portfolio analytics.</EmptyState> : null}
        <div className="cards">
          <KpiCard label="Market value" value={money(positions?.market_value)} detail="Current positions" />
          <KpiCard label={<LearnTerm slug="day-pl">Day P/L</LearnTerm>} value={money(positions?.day_pl)} tone={Number(positions?.day_pl) >= 0 ? "up" : "down"} detail="Current quote, or the stored close" />
          <KpiCard label={<LearnTerm slug="time-weighted-return">Total return</LearnTerm>} value={percent(analytics?.total_return)} tone={Number(analytics?.total_return) >= 0 ? "up" : "down"} />
          <KpiCard label={<LearnTerm slug="volatility">Volatility</LearnTerm>} value={percent(analytics?.volatility)} detail="Historical annualized" />
          <KpiCard label={<LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm>} value={number(analytics?.sharpe_ratio, { maximumFractionDigits: 2 })} detail="From stored daily returns" />
          <KpiCard label={<LearnTerm slug="max-drawdown">Max drawdown</LearnTerm>} value={percent(analytics?.max_drawdown)} tone="down" />
        </div>
        <div className="split-grid">
          <section className="panel">
            <div className="panel-header">
              <div><h2>Live market</h2><p className="muted">Quote worker snapshot</p></div>
              <StatusBadge value={quoteStatus} />
            </div>
            {quoteRows.length === 0 ? <EmptyState title="Waiting for live quotes">Start the quote worker or add watchlist securities.</EmptyState> : (
              <div className="quote-grid">
                {quoteRows.map((quote) => {
                  const change = Number(quote.change);
                  const tone = change > 0 ? "up" : change < 0 ? "down" : "";
                  return <Link className="quote-card" key={quote.ticker} href={`/securities/${quote.ticker}`}>
                    <strong>{quote.ticker}</strong>
                    <p className={`quote-price ${tone}`}>{money(quote.price)}</p>
                    <p className={tone}>{money(quote.change)} · {percent(quote.change_percent)}</p>
                    <small className="muted"><StatusBadge value={quote.timeliness || "unavailable"} /> {quote.source}</small>
                  </Link>;
                })}
              </div>
            )}
          </section>
          <section className="panel">
            <div className="panel-header"><h2>Data operations</h2><StatusBadge value={system?.status || "loading"} /></div>
            <dl className="detail-list">
              <div><dt>Quote provider</dt><dd>{system?.provider?.name || "—"}</dd></div>
              <div><dt>Historical provider</dt><dd>{system?.provider?.historical_provider || "—"}</dd></div>
              <div><dt>Quotes</dt><dd>{system?.provider?.quote_count ?? "—"}</dd></div>
              <div><dt>Last ingestion</dt><dd>{dateTime(system?.ingestion?.finished_at)}</dd></div>
              <div><dt>Ingestion state</dt><dd><StatusBadge value={system?.ingestion?.status || "unavailable"} /></dd></div>
              <div><dt>Failed symbols</dt><dd>{system?.ingestion?.failed_ticker_count ?? "—"}</dd></div>
              <div><dt>Worker</dt><dd><StatusBadge value={system?.worker ? "connected" : "unavailable"} /></dd></div>
            </dl>
          </section>
        </div>
        <div className="split-grid">
          <section className="panel">
            <div className="panel-header"><div><h2>Portfolio value</h2><p className="muted">Backend historical series</p></div><Link href="/portfolio">Full intelligence</Link></div>
            <TimeSeriesChart points={analytics?.series} valueKey="value" label="Portfolio value" format={money} />
          </section>
          <section className="panel">
            <div className="panel-header"><h2>Key insight</h2><span className="muted">Today</span></div>
            {positions?.top_contributors?.[0] ? (
              <div className="insight-card"><p className="eyebrow">Leading contributor</p><strong>{positions.top_contributors[0].ticker}</strong><p className="up">{money(positions.top_contributors[0].day_pl)} day P/L</p><p className="muted">{percent(positions.top_contributors[0].weight)} of current value</p></div>
            ) : positions?.top_detractors?.[0] ? (
              <div className="insight-card"><p className="eyebrow">Largest detractor</p><strong>{positions.top_detractors[0].ticker}</strong><p className="down">{money(positions.top_detractors[0].day_pl)} day P/L</p></div>
            ) : <EmptyState title="No daily mover">Previous-close data is needed for a daily insight.</EmptyState>}
          </section>
        </div>
        <section className="panel">
          <div className="panel-header"><div><h2>Portfolio allocation</h2><p className="muted">Existing backend analytics</p></div><Link href="/portfolio">View positions</Link></div>
          {!analytics?.allocation?.length ? <EmptyState title="No allocation data">Add transactions to calculate portfolio allocation.</EmptyState> : (
            <div className="table-wrap"><table><thead><tr><th>Ticker</th><th className="numeric">Weight</th><th className="numeric">Price</th><th className="numeric">Market value</th></tr></thead>
              <tbody>{analytics.allocation.map((row) => <tr key={row.ticker}><td><Link className="ticker-link" href={`/securities/${row.ticker}`}>{row.ticker}</Link></td><td className="numeric">{percent(row.weight)}</td><td className="numeric">{money(row.price)}</td><td className="numeric">{money(row.market_value)}</td></tr>)}</tbody>
            </table></div>
          )}
        </section>
        <section className="panel">
          <div className="panel-header"><h2>Recent jobs</h2><span className="muted">{jobs.length} runs</span></div>
          {jobs.length === 0 ? <EmptyState title="No job history">Ingestion runs will appear here.</EmptyState> : (
            <div className="table-wrap"><table><thead><tr><th>Job</th><th>Status</th><th>Provider</th><th>Started</th><th className="numeric">Upserted</th></tr></thead>
              <tbody>{jobs.map((job) => <tr key={job.id}><td>{job.job_name}</td><td><StatusBadge value={job.status} /></td><td>{job.provider || "—"}</td><td>{dateTime(job.started_at)}</td><td className="numeric">{job.upserted}</td></tr>)}</tbody>
            </table></div>
          )}
        </section>
      </main>
    </>
  );
}
