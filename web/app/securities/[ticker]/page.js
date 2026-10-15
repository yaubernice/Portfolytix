"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import LearnTerm from "../../../components/LearnTerm";
import Nav from "../../../components/Nav";
import NewsList from "../../../components/NewsList";
import {
  dateTime,
  EmptyState,
  ErrorState,
  money,
  number,
  percent,
  Skeleton,
  Toast,
} from "../../../components/UI";
import { api } from "../../../lib/api";

const PERIODS = ["1D", "1W", "1M", "3M", "1Y", "MAX"];

function quoteStatus(quote) {
  if (!quote) return "UNAVAILABLE";
  const value = String(quote.timeliness || "").toLowerCase();
  if (value === "realtime" || value === "live") return "LIVE";
  if (value === "simulated") return "SIMULATED";
  if (value === "stale" || quote.is_stale) return "STALE";
  if (value === "delayed") return "DELAYED";
  if (value === "historical") return "HISTORICAL";
  return "UNAVAILABLE";
}

function ageLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "unknown age";
  if (value < 60) return `${Math.round(value)}s old`;
  if (value < 3600) return `${Math.round(value / 60)}m old`;
  return `${Math.round(value / 3600)}h old`;
}

function Metric({ label, value, learn, ticker }) {
  const shown = learn ? <LearnTerm slug={learn} ticker={ticker}>{label}</LearnTerm> : label;
  return <div><dt>{shown}</dt><dd>{value}</dd></div>;
}

function FundamentalGroup({ title, children }) {
  return <article className="fundamental-group"><h3>{title}</h3><dl className="detail-list">{children}</dl></article>;
}

function HistoryChart({ prices, ticker }) {
  const rows = prices || [];
  const points = rows.map((row) => Number(row.close)).filter(Number.isFinite);
  if (!points.length) return <EmptyState title="No historical data">No stored PostgreSQL bars exist for this period.</EmptyState>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const coordinates = points.map((value, index) => {
    const x = points.length === 1 ? 50 : (index / (points.length - 1)) * 100;
    const y = 92 - ((value - min) / span) * 84;
    return `${x},${y}`;
  }).join(" ");
  return (
    <>
      <div className="history-chart" role="img" aria-label={`${ticker} adjusted closing prices, from ${rows[0].date} to ${rows[rows.length - 1].date}`}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {points.length > 1 ? <polyline points={coordinates} fill="none" stroke="currentColor" strokeWidth="1.7" vectorEffect="non-scaling-stroke" /> : null}
          {points.length === 1 ? <circle cx="50" cy="50" r="2.5" fill="currentColor" /> : null}
        </svg>
        <div className="chart-range"><span>{rows[0].date}</span><strong>{money(rows[rows.length - 1].close)}</strong><span>{rows[rows.length - 1].date}</span></div>
      </div>
      <details className="chart-data">
        <summary>View chart data table ({rows.length} observations)</summary>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th className="numeric">Adjusted close</th><th className="numeric">Volume</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.date}><td>{row.date}</td><td className="numeric">{money(row.close)}</td><td className="numeric">{number(row.volume)}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </>
  );
}

export default function SecurityPage() {
  const params = useParams();
  const ticker = String(params?.ticker || "").toUpperCase();
  const [period, setPeriod] = useState("1M");
  const [profile, setProfile] = useState(null);
  const [news, setNews] = useState(null);
  const [watchlists, setWatchlists] = useState([]);
  const [portfolios, setPortfolios] = useState([]);
  const [watchlistId, setWatchlistId] = useState("");
  const [portfolioId, setPortfolioId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [price, setPrice] = useState("");
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState({ message: "", tone: "success" });

  const load = useCallback(async (selectedPeriod, initial = false) => {
    if (!ticker) return;
    initial ? setLoading(true) : setHistoryLoading(true);
    setError("");
    try {
      const limit = selectedPeriod === "MAX" ? 5000 : 500;
      const [nextProfile, nextNews] = await Promise.all([
        api(`/securities/${encodeURIComponent(ticker)}?period=${selectedPeriod}&history_limit=${limit}${initial ? "&ensure_history=true" : ""}`),
        initial ? api(`/news?ticker=${encodeURIComponent(ticker)}`).catch(() => null) : Promise.resolve(news),
      ]);
      setProfile(nextProfile);
      if (initial) {
        setNews(nextNews);
        const defaultPrice = nextProfile.live_quote?.price;
        if (defaultPrice) setPrice(String(defaultPrice));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setHistoryLoading(false);
    }
  }, [news, ticker]);

  useEffect(() => {
    load("1M", true);
    Promise.all([api("/watchlists?limit=100"), api("/portfolios")])
      .then(([listBody, portfolioRows]) => {
        setWatchlists(listBody.items || []);
        setWatchlistId(listBody.items?.[0]?.id || "");
        setPortfolios(portfolioRows || []);
        setPortfolioId(portfolioRows?.[0]?.id || "");
      })
      .catch((err) => setError(err.message));
  }, [ticker]); // eslint-disable-line react-hooks/exhaustive-deps

  const quote = profile?.live_quote;
  const bars = profile?.prices || [];
  const lastBar = bars.length ? bars[bars.length - 1] : null;
  const priorBar = bars.length > 1 ? bars[bars.length - 2] : null;
  const usingClose = !quote && lastBar;
  const shownPrice = quote?.price ?? lastBar?.close;
  const priorClose = quote?.previous_close ?? priorBar?.close;
  const change = shownPrice != null && priorClose != null ? Number(shownPrice) - Number(priorClose) : null;
  const status = usingClose ? "HISTORICAL" : quoteStatus(quote);
  const changeTone = change > 0 ? "up" : change < 0 ? "down" : "";
  const freshnessTitle = quote
    ? `Source: ${quote.source}; timestamp: ${dateTime(quote.provider_timestamp || quote.timestamp)}; ${ageLabel(quote.age_seconds)}`
    : usingClose
      ? `Stored close from ${profile.history_source || "the historical provider"}. This is not a live quote.`
      : "No current quote is available";
  const fundamentals = useMemo(() => profile ? [
    ["Valuation", [["P/E ratio", number(profile.pe_ratio), "pe-ratio"], ["Price / book", number(profile.price_to_book)], ["Price / sales", number(profile.price_to_sales)], ["EPS", money(profile.eps, profile.currency)]]],
    ["Profitability", [["ROE", percent(profile.roe), "roe"], ["ROA", percent(profile.roa)], ["Profit margin", percent(profile.profit_margin)], ["EBITDA", money(profile.ebitda, profile.currency)]]],
    ["Growth", [["Revenue growth", percent(profile.revenue_growth)], ["Earnings growth", percent(profile.earnings_growth)]]],
    ["Scale", [["Market cap", money(profile.market_cap, profile.currency)], ["Revenue", money(profile.revenue, profile.currency)], ["Shares outstanding", number(profile.shares_outstanding)]]],
    ["Income & risk", [["Dividend yield", percent(profile.dividend_yield)], ["Beta", number(profile.beta)]]],
  ] : [], [profile, ticker]);

  async function addToWatchlist(event) {
    event.preventDefault();
    if (!watchlistId) return;
    setSubmitting(true);
    try {
      await api(`/watchlists/${watchlistId}/items`, { method: "POST", body: JSON.stringify({ security_id: profile.security_id }) });
      setToast({ message: `${ticker} added to watchlist`, tone: "success" });
    } catch (err) {
      setToast({ message: err.message, tone: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  async function addToPortfolio(event) {
    event.preventDefault();
    if (!portfolioId) return;
    setSubmitting(true);
    try {
      await api(`/portfolios/${portfolioId}/transactions`, {
        method: "POST",
        body: JSON.stringify({ ticker, transaction_type: "BUY", quantity, price }),
      });
      setToast({ message: `${ticker} purchase added to portfolio`, tone: "success" });
    } catch (err) {
      setToast({ message: err.message, tone: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        {loading ? <div className="panel"><Skeleton lines={8} label={`Loading ${ticker}`} /></div> : null}
        <ErrorState message={error} retry={() => load(period, !profile)} />
        {!loading && profile ? (
          <div className="stack">
            <header className="page-header security-header">
              <div><p className="eyebrow">Security</p><h1>{profile.ticker} <span>{profile.name}</span></h1><p className="muted">{profile.exchange} · {profile.sector || "Sector unavailable"} · {profile.currency}</p></div>
              <span className={`quote-status quote-status-${status.toLowerCase()}`} title={freshnessTitle} aria-label={`${status}. ${freshnessTitle}`}>{status} <span aria-hidden="true">ⓘ</span></span>
            </header>

            <section className="current-quote" aria-labelledby="current-quote-title">
              <div><p className="eyebrow" id="current-quote-title">{usingClose ? "Latest close" : "Current quote"}</p><p className="current-price">{shownPrice != null ? money(shownPrice, profile.currency) : "Unavailable"}</p><p className={changeTone}>{quote ? `${money(quote.change, profile.currency)} (${percent(quote.change_percent)}) today` : usingClose ? "Stored daily close, not a live quote" : "No price is stored for this symbol yet"}</p></div>
              <dl className="quote-details">
                <Metric label="Volume" value={number(quote?.volume ?? (usingClose ? lastBar.volume : null))} />
                <Metric label="Previous close" value={money(priorClose, profile.currency)} />
                <Metric label="Bid" value={money(quote?.bid, profile.currency)} />
                <Metric label="Ask" value={money(quote?.ask, profile.currency)} />
              </dl>
              <p className="quote-source" title={freshnessTitle}>{quote ? `${quote.source} · market ${dateTime(quote.provider_timestamp || quote.timestamp)} · received ${dateTime(quote.received_at)} · print ${ageLabel(quote.age_seconds)}` : usingClose ? `${profile.history_source || "stored"} · session ${dateTime(profile.latest_close_at)} · historical close` : "No live quote is published for this symbol, and the historical provider returned no daily price."}</p>
            </section>

            <div className="split-grid">
              <div className="stack">
                <section className="panel" aria-labelledby="history-title">
                  <div className="panel-header"><div><h2 id="history-title">Historical adjusted close</h2><p className="muted">Stored daily bars. The session date is not a live quote time.</p></div><span className={`status ${profile.history_is_stale ? "status-negative" : "status-neutral"}`}>{profile.history_timeliness === "unavailable" ? "unavailable" : profile.history_is_stale ? "historical, stale" : "historical"}</span></div>
                  <div className="period-tabs" role="group" aria-label="History period">
                    {PERIODS.map((value) => <button type="button" key={value} aria-pressed={period === value} disabled={historyLoading} onClick={() => { setPeriod(value); load(value); }}>{value}</button>)}
                  </div>
                  {historyLoading ? <Skeleton lines={4} label="Loading history" /> : <HistoryChart prices={profile.prices} ticker={ticker} />}
                  <p className="metadata">Source: {profile.history_source || "unavailable"} · Updated: {dateTime(profile.history_updated_at)} · Latest bar: {dateTime(profile.latest_close_at)}</p>
                </section>

                <section className="panel" aria-labelledby="fundamentals-title">
                  <div className="panel-header"><div><h2 id="fundamentals-title">Fundamentals</h2><p className="muted">Complete available provider snapshot, grouped by category.</p></div></div>
                  <div className="fundamentals-grid">{fundamentals.map(([title, values]) => <FundamentalGroup title={title} key={title}>{values.map(([label, value, learn]) => <Metric key={label} label={label} value={value} learn={learn} ticker={ticker} />)}</FundamentalGroup>)}</div>
                  <p className="metadata">Provider: {profile.fundamentals_provider || profile.provider || "unavailable"} · As of: {profile.as_of || "unavailable"} · Updated: {dateTime(profile.fundamentals_updated_at)}</p>
                </section>

                <section className="panel" aria-labelledby="news-title">
                  <div className="panel-header"><div><h2 id="news-title">Recent news</h2><p className="muted">Provider: {news?.provider || "none"}</p></div></div>
                  {!news?.items?.length ? <EmptyState title="No recent provider news">No headlines are available for this security.</EmptyState> : <NewsList items={news.items} provider={news.provider} />}
                </section>
              </div>

              <aside className="stack" aria-label="Security actions">
                <section className="panel"><h2>Add to watchlist</h2>{watchlists.length ? <form onSubmit={addToWatchlist}><label className="field">Watchlist<select value={watchlistId} onChange={(event) => setWatchlistId(event.target.value)}>{watchlists.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><button className="primary" disabled={submitting} type="submit">Add {ticker}</button></form> : <EmptyState title="No watchlists">Create a watchlist before adding this security.</EmptyState>}</section>
                <section className="panel"><h2>Add to portfolio</h2>{portfolios.length ? <form onSubmit={addToPortfolio}><label className="field">Portfolio<select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>{portfolios.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="field">Quantity<input type="number" min="0.00000001" step="any" required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label className="field">Price ({profile.currency})<input type="number" min="0.000001" step="any" required value={price} onChange={(event) => setPrice(event.target.value)} /></label><p className="muted">Creates a BUY transaction. Price defaults to the current quote when available.</p><button className="primary" disabled={submitting} type="submit">Add transaction</button></form> : <EmptyState title="No portfolios">Create a portfolio before adding a transaction.</EmptyState>}</section>
                <section className="panel"><h2>Reference metadata</h2><dl className="detail-list"><Metric label="Asset type" value={profile.asset_type} /><Metric label="Industry" value={profile.industry || "—"} /><Metric label="Country" value={profile.country || "—"} /><Metric label="MIC" value={profile.mic || "—"} /><Metric label="Profile provider" value={profile.provider} /><Metric label="Provider symbol" value={profile.provider_symbol || "—"} /></dl></section>
              </aside>
            </div>
          </div>
        ) : null}
      </main>
      <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast({ message: "", tone: "success" })} />
    </>
  );
}
