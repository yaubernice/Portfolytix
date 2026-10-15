"use client";

import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import PortfolioAssistant from "../../components/PortfolioAssistant";
import {
  AllocationChart,
  EmptyState,
  ErrorState,
  KpiCard,
  money,
  number,
  percent,
  Skeleton,
  StatusBadge,
  TimeSeriesChart,
  Toast,
} from "../../components/UI";
import { api } from "../../lib/api";

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [positions, setPositions] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [toast, setToast] = useState("");

  useEffect(() => {
    api("/portfolios").then((rows) => {
      setPortfolios(rows);
      if (rows[0]) setPortfolioId(rows[0].id);
      else setLoading(false);
    }).catch((err) => {
      setError(err.message);
      setLoading(false);
    });
  }, []);

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
      setPortfolioId(created.id);
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

  useEffect(() => {
    if (portfolioId) sessionStorage.setItem("finsight_portfolio", portfolioId);
  }, [portfolioId]);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Portfolio intelligence</p><h1>Performance &amp; positions</h1><p className="muted">Backend-calculated performance, risk, and live position intelligence.</p></div>
          <label className="field">Portfolio<select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>{portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        </header>
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Your portfolios</h2>
              <p className="muted">Create one here, then add a buy from a security page.</p>
            </div>
          </div>
          <form className="row" onSubmit={createPortfolio}>
            <label className="sr-only" htmlFor="portfolio-name">New portfolio name</label>
            <input id="portfolio-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="New portfolio name" maxLength={200} required />
            <label className="sr-only" htmlFor="portfolio-description">Description</label>
            <input id="portfolio-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description (optional)" maxLength={500} />
            <button className="primary" type="submit">Create portfolio</button>
          </form>
        </section>
        <ErrorState message={error} />
        {!loading && portfolios.length === 0 ? <EmptyState title="No portfolios yet">Create one above. Positions come from buy and sell transactions.</EmptyState> : null}
        <div className="cards">
          <KpiCard label="Market value" value={money(positions?.market_value)} detail="Live marked positions" />
          <KpiCard label={<LearnTerm slug="day-pl">Day P/L</LearnTerm>} value={money(positions?.day_pl)} tone={Number(positions?.day_pl) >= 0 ? "up" : "down"} detail="Cash-flow adjusted" />
          <KpiCard label={<LearnTerm slug="unrealized-pl">Unrealized P/L</LearnTerm>} value={money(positions?.unrealized_pl)} tone={Number(positions?.unrealized_pl) >= 0 ? "up" : "down"} detail={`Cost basis ${money(positions?.cost_basis)}`} />
          <KpiCard label={<LearnTerm slug="time-weighted-return">Time-weighted return</LearnTerm>} value={percent(analytics?.total_return)} tone={Number(analytics?.total_return) >= 0 ? "up" : "down"} detail="Cash flows removed, not annualized" />
          <KpiCard label={<LearnTerm slug="volatility">Volatility</LearnTerm>} value={percent(analytics?.volatility)} detail="Historical annualized" />
          <KpiCard label={<LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm>} value={number(analytics?.sharpe_ratio, { maximumFractionDigits: 2 })} detail="Stored daily returns" />
          <KpiCard label={<LearnTerm slug="max-drawdown">Max drawdown</LearnTerm>} value={percent(analytics?.max_drawdown)} tone="down" detail="Peak-to-trough TWR" />
        </div>
        <div className="portfolio-chart-grid">
          <section className="panel"><div className="panel-header"><h2>Value over time</h2><span className="muted">{analytics?.observation_count ?? 0} return observations</span></div><TimeSeriesChart points={analytics?.series} valueKey="value" label="Portfolio value" format={money} /></section>
          <section className="panel"><div className="panel-header"><h2><LearnTerm slug="time-weighted-return">Cumulative return</LearnTerm></h2><span className="muted">Backend TWR</span></div><TimeSeriesChart points={analytics?.series} valueKey="cumulative_return" label="Cumulative return" format={percent} /></section>
          <section className="panel"><div className="panel-header"><h2>Daily P/L</h2><span className="muted">External cash flows removed</span></div><TimeSeriesChart points={analytics?.series} valueKey="daily_pl" label="Daily P/L" format={money} /></section>
          <section className="panel"><div className="panel-header"><h2><LearnTerm slug="max-drawdown">Drawdown</LearnTerm></h2><span className="muted">Point-in-time TWR drawdown</span></div><TimeSeriesChart points={analytics?.series} valueKey="drawdown" label="Drawdown" format={percent} tone="down" /></section>
        </div>
        <div className="split-grid">
          <section className="panel"><div className="panel-header"><h2>Allocation</h2><span className="muted">Backend market values</span></div><AllocationChart rows={analytics?.allocation} /></section>
          <section className="panel">
            <div className="panel-header"><h2>Today&apos;s movers</h2><span className="muted">Ranked by day P/L</span></div>
            <div className="movers-grid">
              <div><h3 className="up">Top contributors</h3>{positions?.top_contributors?.length ? positions.top_contributors.map((row) => <div className="mover-row" key={`up-${row.ticker}`}><strong>{row.ticker}</strong><span className="up">{money(row.day_pl)}</span></div>) : <p className="muted">No positive contributors.</p>}</div>
              <div><h3 className="down">Top detractors</h3>{positions?.top_detractors?.length ? positions.top_detractors.map((row) => <div className="mover-row" key={`down-${row.ticker}`}><strong>{row.ticker}</strong><span className="down">{money(row.day_pl)}</span></div>) : <p className="muted">No detractors.</p>}</div>
            </div>
          </section>
        </div>
        <section className="panel">
          <div className="panel-header"><div><h2>Positions</h2><p className="muted">Live prices refresh every five seconds</p></div></div>
          {loading ? <Skeleton lines={6} /> : null}
          {!loading && !positions?.positions?.length ? <EmptyState title="No positions">Add transactions to build this portfolio.</EmptyState> : null}
          {!loading && positions?.positions?.length ? <div className="table-wrap"><table>
            <thead><tr><th>Ticker</th><th className="numeric">Quantity</th><th className="numeric">Average cost</th><th className="numeric">Cost basis</th><th className="numeric">Current price</th><th className="numeric">Market value</th><th className="numeric"><LearnTerm slug="unrealized-pl">Unrealized P/L</LearnTerm></th><th className="numeric"><LearnTerm slug="day-pl">Day P/L</LearnTerm></th><th className="numeric">Weight</th><th>Freshness</th></tr></thead>
            <tbody>{positions.positions.map((row) => <tr key={row.ticker}><td>{row.ticker}</td><td className="numeric">{number(row.quantity, { maximumFractionDigits: 6 })}</td><td className="numeric">{money(row.average_cost)}</td><td className="numeric">{money(row.cost_basis)}</td><td className="numeric">{money(row.current_price)}</td><td className="numeric">{money(row.market_value)}</td><td className={`numeric ${Number(row.unrealized_pl) >= 0 ? "up" : "down"}`}>{money(row.unrealized_pl)}</td><td className={`numeric ${Number(row.day_pl) >= 0 ? "up" : "down"}`}>{money(row.day_pl)}</td><td className="numeric">{percent(row.weight)}</td><td><StatusBadge value={row.freshness?.timeliness || "unavailable"} /><small className="freshness-detail">{row.freshness?.source}{row.freshness?.age_seconds != null ? ` · ${number(row.freshness.age_seconds, { maximumFractionDigits: 0 })}s` : ""}</small></td></tr>)}</tbody>
          </table></div> : null}
        </section>
        {portfolioId ? <PortfolioAssistant portfolioId={portfolioId} /> : null}
        <Toast message={toast} onDismiss={() => setToast("")} />
      </main>
    </>
  );
}
