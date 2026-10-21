"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import PortfolioAssistant from "../../components/PortfolioAssistant";
import { usePortfolio } from "../../components/usePortfolio";
import {
  AllocationChart,
  AttentionMark,
  EmptyState,
  ErrorState,
  KpiCard,
  money,
  number,
  percent,
  Skeleton,
  StatusBadge,
  TickerIdentity,
  TimeSeriesChart,
  Toast,
} from "../../components/UI";
import { api } from "../../lib/api";
import { sharpeNote, volatilityNote } from "../../lib/figures";

function signedTone(value) {
  if (value == null || value === "") return "";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount === 0) return "";
  return amount > 0 ? "up" : "down";
}

export default function PortfolioPage() {
  const { portfolios, setPortfolios, portfolioId, selectPortfolio, ready, error: portfolioError } = usePortfolio();
  const [positions, setPositions] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (ready && !portfolioId) setLoading(false);
  }, [ready, portfolioId]);

  async function createPortfolio(event) {
    event.preventDefault();
    if (!name.trim()) return;
    setError("");
    try {
      const created = await api("/portfolios", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
        }),
      });
      setPortfolios((current) => [...current, created]);
      selectPortfolio(created.id);
      setName("");
      setDescription("");
      setToast("Portfolio created");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    if (!portfolioId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    api(`/portfolios/${portfolioId}/analytics`)
      .then((body) => { if (!cancelled) setAnalytics(body); })
      .catch((err) => {
        if (cancelled) return;
        setAnalytics(null);
        if (!/no transactions/i.test(err.message)) setError(err.message);
      });
    const loadPositions = () => api(`/portfolios/${portfolioId}/positions`)
      .then((body) => { if (!cancelled) setPositions(body); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    loadPositions();
    const timer = setInterval(loadPositions, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [portfolioId]);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Portfolio intelligence</p><h1>Performance and positions</h1><p className="muted">Value, risk, and positions are calculated from stored transactions and prices. A short return history is labeled on the card. Choose the portfolio in the top bar.</p></div></header>
        <ErrorState message={error || portfolioError} />
        {!loading && portfolios.length === 0 ? (
          <section className="panel">
            <h2>Create a portfolio</h2>
            <p className="muted">Then buy a share from a company page.</p>
            <form className="row" onSubmit={createPortfolio}>
              <label className="sr-only" htmlFor="portfolio-name">New portfolio name</label>
              <input id="portfolio-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="New portfolio name" maxLength={200} required />
              <label className="sr-only" htmlFor="portfolio-description">Description</label>
              <input id="portfolio-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description (optional)" maxLength={500} />
              <button className="primary" type="submit">Create portfolio</button>
            </form>
          </section>
        ) : null}
        {portfolios.length ? (
        <div className="cards">
          <KpiCard label="Market value" value={money(positions?.market_value)} detail="Latest provider quote" />
          <KpiCard label={<LearnTerm slug="day-pl">Day P/L</LearnTerm>} value={positions?.day_pl == null ? "—" : money(positions.day_pl)} tone={Number(positions?.day_pl) < 0 ? "down" : Number(positions?.day_pl) > 0 ? "up" : ""} alert={Number(positions?.day_pl) < 0} detail={positions?.day_pl == null ? "No previous close yet." : "Change since the previous close, cash flows removed."} />
          <KpiCard label={<LearnTerm slug="unrealized-pl">Unrealized P/L</LearnTerm>} value={positions?.unrealized_pl == null ? "—" : money(positions.unrealized_pl)} tone={Number(positions?.unrealized_pl) < 0 ? "down" : Number(positions?.unrealized_pl) > 0 ? "up" : ""} alert={Number(positions?.unrealized_pl) < 0} detail={positions?.cost_basis == null ? "No cost basis yet." : `Cost basis ${money(positions.cost_basis)}`} />
          <KpiCard label={<LearnTerm slug="time-weighted-return">Time-weighted return</LearnTerm>} value={analytics?.total_return == null ? "—" : percent(analytics.total_return)} tone={Number(analytics?.total_return) < 0 ? "down" : Number(analytics?.total_return) > 0 ? "up" : ""} alert={Number(analytics?.total_return) < 0} detail={analytics?.total_return == null ? "Not enough stored daily history." : "Cash flows removed, not annualized."} />
          <KpiCard label={<LearnTerm slug="volatility">Volatility</LearnTerm>} value={analytics?.volatility == null ? "—" : percent(analytics.volatility)} detail={volatilityNote(analytics)} />
          <KpiCard label={<LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm>} value={analytics?.sharpe_ratio == null ? "—" : number(analytics.sharpe_ratio, { maximumFractionDigits: 2 })} detail={sharpeNote(analytics)} />
          <KpiCard label={<LearnTerm slug="max-drawdown">Max drawdown</LearnTerm>} value={analytics?.max_drawdown == null ? "—" : percent(analytics.max_drawdown)} tone={Number(analytics?.max_drawdown) < 0 ? "down" : ""} alert={Number(analytics?.max_drawdown) < 0} detail={analytics?.max_drawdown == null ? "Needs a longer stored return series." : "Peak-to-trough on the return index."} />
        </div>
        ) : null}
        {loading ? <Skeleton lines={4} label="Loading portfolio record" /> : null}
        {!loading && analytics?.series?.filter((point) => point.value != null).length >= 2 ? (
          <div className="portfolio-chart-grid">
            <section className="panel"><div className="panel-header"><h2>Value over time</h2><span className="muted">{analytics?.observation_count ?? 0} return observations</span></div><TimeSeriesChart points={analytics.series} valueKey="value" label="Portfolio value" format={money} /></section>
            <section className="panel"><div className="panel-header"><h2><LearnTerm slug="time-weighted-return">Cumulative return</LearnTerm></h2><span className="muted">Backend TWR</span></div><TimeSeriesChart points={analytics.series} valueKey="cumulative_return" label="Cumulative return" format={percent} /></section>
            <section className="panel"><div className="panel-header"><h2>Daily P/L</h2><span className="muted">External cash flows removed</span></div><TimeSeriesChart points={analytics.series} valueKey="daily_pl" label="Daily P/L" format={money} /></section>
            <section className="panel"><div className="panel-header"><h2><LearnTerm slug="max-drawdown">Drawdown</LearnTerm></h2><span className="muted">Point-in-time TWR drawdown</span></div><TimeSeriesChart points={analytics.series} valueKey="drawdown" label="Drawdown" format={percent} tone="down" /></section>
          </div>
        ) : null}
        {!loading && portfolioId && !analytics ? <p className="compact-note">Stored daily history is not available for this portfolio yet. Buy a share, then the nightly history job fills the closes.</p> : null}
        <div className="split-grid">
          <section className="panel"><div className="panel-header"><h2>Allocation</h2><span className="muted">Backend market values</span></div>{analytics?.allocation?.length ? <AllocationChart rows={analytics.allocation} /> : <p className="compact-note">{loading ? "Loading allocation." : "Buy at least one share to see how the portfolio is split."}</p>}</section>
          <section className="panel">
            <div className="panel-header"><h2>Today&apos;s movers</h2><span className="muted">Ranked by day P/L</span></div>
            <div className="movers-grid">
              <div><h3 className="up">Top contributors</h3>{positions?.top_contributors?.length ? positions.top_contributors.map((row) => <div className="mover-row" key={`up-${row.ticker}`}><TickerIdentity ticker={row.ticker} size={22} /><span className="up">{money(row.day_pl)}</span></div>) : <p className="muted">No positive contributors.</p>}</div>
              <div><h3 className="down">Top detractors</h3>{positions?.top_detractors?.length ? positions.top_detractors.map((row) => <div className="mover-row" key={`down-${row.ticker}`}><TickerIdentity ticker={row.ticker} size={22} /><span className="down"><AttentionMark />{money(row.day_pl)}</span></div>) : <p className="muted">No detractors.</p>}</div>
            </div>
          </section>
        </div>
        <section className="panel">
          <div className="panel-header"><div><h2>Positions</h2><p className="muted">The table reloads every five seconds. Delayed quotes stay delayed.</p></div></div>
          {loading ? <Skeleton lines={6} /> : null}
          {!loading && !positions?.positions?.length ? <EmptyState title="No positions">Add transactions to build this portfolio.</EmptyState> : null}
          {!loading && positions?.positions?.length ? <div className="table-wrap"><table>
            <thead><tr><th>Ticker</th><th className="numeric">Quantity</th><th className="numeric">Average cost</th><th className="numeric">Cost basis</th><th className="numeric">Current price</th><th className="numeric">Market value</th><th className="numeric"><LearnTerm slug="unrealized-pl">Unrealized P/L</LearnTerm></th><th className="numeric"><LearnTerm slug="day-pl">Day P/L</LearnTerm></th><th className="numeric">Weight</th><th>Freshness</th></tr></thead>
            <tbody>{positions.positions.map((row) => <tr key={row.ticker}><td><Link className="ticker-link" href={`/securities/${row.ticker}`}><TickerIdentity ticker={row.ticker} size={24} /></Link></td><td className="numeric">{number(row.quantity, { maximumFractionDigits: 6 })}</td><td className="numeric">{money(row.average_cost)}</td><td className="numeric">{money(row.cost_basis)}</td><td className="numeric">{money(row.current_price)}</td><td className="numeric">{money(row.market_value)}</td><td className={`numeric ${signedTone(row.unrealized_pl)}`}>{Number(row.unrealized_pl) < 0 ? <AttentionMark /> : null}{money(row.unrealized_pl)}</td><td className={`numeric ${signedTone(row.day_pl)}`}>{Number(row.day_pl) < 0 ? <AttentionMark /> : null}{money(row.day_pl)}</td><td className="numeric">{percent(row.weight)}</td><td><StatusBadge value={row.freshness?.timeliness || "unavailable"} /><small className="freshness-detail">{row.freshness?.source}{row.freshness?.age_seconds != null ? ` · ${number(row.freshness.age_seconds, { maximumFractionDigits: 0 })}s` : ""}</small></td></tr>)}</tbody>
          </table></div> : null}
        </section>
        {portfolios.length ? (
          <details className="panel">
            <summary>Create another portfolio</summary>
            <form className="row" onSubmit={createPortfolio}>
              <label className="sr-only" htmlFor="portfolio-name">New portfolio name</label>
              <input id="portfolio-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="New portfolio name" maxLength={200} required />
              <label className="sr-only" htmlFor="portfolio-description">Description</label>
              <input id="portfolio-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description (optional)" maxLength={500} />
              <button className="primary" type="submit">Create portfolio</button>
            </form>
          </details>
        ) : null}
        {portfolioId ? <PortfolioAssistant portfolioId={portfolioId} /> : null}
        <Toast message={toast} onDismiss={() => setToast("")} />
      </main>
    </>
  );
}
