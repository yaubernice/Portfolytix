"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { usePortfolio } from "../../components/usePortfolio";
import {
  AllocationChart,
  AttentionMark,
  CompanyLogo,
  EmptyState,
  ErrorState,
  money,
  number,
  percent,
  Skeleton,
  TickerIdentity,
  TimeSeriesChart,
  dateTime,
} from "../../components/UI";
import { api } from "../../lib/api";
import { sharpeNote, volatilityNote } from "../../lib/figures";

export default function DashboardPage() {
  const { portfolios, portfolioId, ready, error: portfolioError } = usePortfolio();
  const [analytics, setAnalytics] = useState(null);
  const [historyNote, setHistoryNote] = useState("");
  const [positions, setPositions] = useState(null);
  const [listedQuotes, setListedQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return undefined;
    if (!portfolioId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setError("");
    setHistoryNote("");
    api(`/portfolios/${portfolioId}/analytics`)
      .then((body) => {
        if (!cancelled) setAnalytics(body);
      })
      .catch((err) => {
        if (!cancelled) {
          setAnalytics(null);
          setHistoryNote(err.message);
        }
      });
    const loadPositions = () => {
      api(`/portfolios/${portfolioId}/positions`)
        .then((body) => {
          if (!cancelled) setPositions(body);
        })
        .catch((err) => {
          if (!cancelled) {
            setPositions(null);
            setError(err.message);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };
    loadPositions();
    const timer = setInterval(loadPositions, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [portfolioId, ready]);

  useEffect(() => {
    let cancelled = false;
    async function loadListed() {
      const symbols = new Set((positions?.positions || []).map((row) => row.ticker).filter(Boolean));
      try {
        const page = await api("/watchlists?limit=100");
        const details = await Promise.all(
          (page.items || []).slice(0, 5).map((list) => api(`/watchlists/${list.id}?limit=100`)),
        );
        for (const detail of details) {
          for (const item of detail.items || []) {
            if (item.ticker) symbols.add(item.ticker);
          }
        }
      } catch {
        // Holdings can still fill the list.
      }
      const tickers = [...symbols].slice(0, 8);
      if (!tickers.length) {
        if (!cancelled) setListedQuotes([]);
        return;
      }
      try {
        const body = await api(`/quotes?tickers=${encodeURIComponent(tickers.join(","))}`);
        if (!cancelled) setListedQuotes(body.quotes || []);
      } catch {
        if (!cancelled) setListedQuotes([]);
      }
    }
    loadListed();
    const timer = setInterval(loadListed, 20000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [positions]);

  const portfolio = portfolios.find((row) => row.id === portfolioId);
  const series = (analytics?.series || []).filter((point) => point.value !== null && point.value !== undefined);
  const quote = listedQuotes[0];
  const mark = positions?.positions?.find((row) => row.freshness)?.freshness;
  const timeliness = String(quote?.timeliness || mark?.timeliness || "").toLowerCase();
  const quoteKind = timeliness === "realtime" || timeliness === "live" ? "Real-time quote" : timeliness === "delayed" ? "Delayed quote" : timeliness ? `${timeliness} quote` : "";
  const stamp = quote?.provider_timestamp || quote?.timestamp || mark?.as_of;
  const freshness = quoteKind
    ? `${quoteKind} · ${quote?.source || mark?.source || "source unavailable"}${stamp ? ` · as of ${dateTime(stamp)}` : ""}. Positions reload every 5 seconds. That reload does not make a delayed quote real-time.`
    : "";
  const contributors = positions?.top_contributors || [];
  const detractors = positions?.top_detractors || [];

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">{portfolio?.name || "Portfolio"}</p>
            <h1>How this portfolio stands</h1>
            <p className="muted">{freshness || "Waiting for a provider quote."} These figures are calculated from stored transactions and prices. They are not a forecast and not a buy or sell instruction. <Link href="/data">Data status</Link></p>
          </div>
        </header>
        <ErrorState message={error || portfolioError} />
        {loading && portfolioId ? <Skeleton lines={3} label="Loading dashboard" /> : null}
        {!loading && ready && portfolios.length === 0 ? <EmptyState title="No portfolio yet">Create one on the Portfolio page, then buy a share from a company page.</EmptyState> : null}
        {portfolioId ? (
          <>
            <section className="hero" aria-labelledby="portfolio-value-title">
              <div className="hero-main">
                <p className="hero-label" id="portfolio-value-title">Portfolio value</p>
                <p className="hero-value">{money(positions?.market_value)}</p>
                <p className="muted">Marked with the latest provider quote. A delayed quote stays delayed between reloads.</p>
              </div>
              <dl className="hero-side">
                <div>
                  <dt><LearnTerm slug="day-pl">Day change</LearnTerm></dt>
                  <dd className={positions?.day_pl == null ? "" : Number(positions.day_pl) < 0 ? "down" : Number(positions.day_pl) > 0 ? "up" : ""}>
                    {Number(positions?.day_pl) < 0 ? <AttentionMark /> : null}
                    {positions?.day_pl == null ? "—" : money(positions.day_pl)}
                  </dd>
                </div>
                <div>
                  <dt><LearnTerm slug="time-weighted-return">Total return</LearnTerm></dt>
                  <dd className={Number(analytics?.total_return) < 0 ? "down" : ""}>{analytics?.total_return == null ? "—" : percent(analytics.total_return)}</dd>
                </div>
              </dl>
            </section>
            <section className="workspace-block" aria-labelledby="history-title">
              <div className="block-head">
                <h2 id="history-title">Value over time</h2>
                <Link href="/portfolio">Open the full record</Link>
              </div>
              {series.length >= 2 ? (
                <>
                  <TimeSeriesChart points={analytics.series} valueKey="value" label="Portfolio value" format={money} />
                  {series[0]?.date && series[series.length - 1]?.date ? (
                    <p className="compact-note chart-caption">
                      Stored daily closes run from {money(series[0].value)} on {series[0].date} to {money(series[series.length - 1].value)} on {series[series.length - 1].date}. Total return and volatility use this series, not the quote above.
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="compact-note">
                  {historyNote || "Stored daily history is still too short for a chart."}
                  {" "}
                  {analytics?.observation_count != null ? `${analytics.observation_count} return observation${analytics.observation_count === 1 ? "" : "s"} so far.` : ""}
                  {" "}
                  The figure above uses the latest provider quote. Daily closes are filled after the US session.
                </p>
              )}
            </section>
            <dl className="metric-strip">
              <div>
                <dt><LearnTerm slug="volatility">Volatility</LearnTerm></dt>
                <dd>{analytics?.volatility == null ? "—" : percent(analytics.volatility)}</dd>
                <p>{analytics?.volatility == null ? "Not enough daily returns to annualize." : volatilityNote(analytics)}</p>
              </div>
              <div>
                <dt><LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm></dt>
                <dd>{analytics?.sharpe_ratio == null ? "—" : number(analytics.sharpe_ratio, { maximumFractionDigits: 2 })}</dd>
                <p>{analytics?.sharpe_ratio == null ? "Needs at least two daily returns." : sharpeNote(analytics)}</p>
              </div>
              <div>
                <dt><LearnTerm slug="max-drawdown">Max drawdown</LearnTerm></dt>
                <dd className={Number(analytics?.max_drawdown) < 0 ? "down" : ""}>
                  {Number(analytics?.max_drawdown) < 0 ? <AttentionMark /> : null}
                  {analytics?.max_drawdown == null ? "—" : percent(analytics.max_drawdown)}
                </dd>
                <p>{analytics?.max_drawdown == null ? "Needs a longer stored return series." : "Peak to trough on the return index."}</p>
              </div>
            </dl>
            <div className="record-grid">
              <section className="workspace-block" aria-labelledby="movers-title">
                <div className="block-head"><h2 id="movers-title">Today&apos;s movers</h2></div>
                {!contributors.length && !detractors.length ? (
                  <p className="compact-note">A previous close is needed before a holding can be called a daily mover.</p>
                ) : (
                  <div className="mover-columns">
                    <div>
                      <h3 className="up">Helped</h3>
                      {contributors.length ? contributors.map((row) => (
                        <Link className="mover-line" key={`up-${row.ticker}`} href={`/securities/${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="up">{money(row.day_pl)}</span>
                        </Link>
                      )) : <p className="muted">No holding is up today.</p>}
                    </div>
                    <div>
                      <h3 className="down">Hurt</h3>
                      {detractors.length ? detractors.map((row) => (
                        <Link className="mover-line" key={`down-${row.ticker}`} href={`/securities/${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="down"><AttentionMark />{money(row.day_pl)}</span>
                        </Link>
                      )) : <p className="muted">No holding is down today.</p>}
                    </div>
                  </div>
                )}
              </section>
              <section className="workspace-block" aria-labelledby="exposure-title">
                <div className="block-head"><h2 id="exposure-title">Where the value sits</h2></div>
                {analytics?.allocation?.length ? <AllocationChart rows={analytics.allocation} /> : <p className="compact-note">Buy at least one share to see how the portfolio is split.</p>}
              </section>
            </div>
            <section className="workspace-block" aria-labelledby="market-title">
              <div className="block-head">
                <h2 id="market-title">Prices in view</h2>
                <p className="muted">Holdings and watchlist symbols. This list reloads every 20 seconds from the latest stored provider quote.</p>
              </div>
              {listedQuotes.length === 0 ? (
                <p className="compact-note">Buy a holding or add a symbol to a watchlist. The latest provider price will show here.</p>
              ) : (
                <ul className="quote-lines">
                  {listedQuotes.map((row) => {
                    const change = Number(row.change);
                    const tone = change > 0 ? "up" : change < 0 ? "down" : "";
                    return (
                      <li key={row.ticker}>
                        <Link href={`/securities/${row.ticker}`}>
                          <CompanyLogo ticker={row.ticker} size={28} />
                          <strong>{row.ticker}</strong>
                          <span className={tone}>{money(row.price)}</span>
                          <span className={tone}>{money(row.change)} · {percent(row.change_percent)}</span>
                          <small>{String(row.timeliness || "").toLowerCase() === "realtime" ? "Real-time" : row.timeliness || "unavailable"} · {row.source || "source unavailable"}</small>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        ) : null}
      </main>
    </>
  );
}
