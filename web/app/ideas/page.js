"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, money, number, percent, Skeleton, Toast } from "../../components/UI";
import { api } from "../../lib/api";

export default function IdeasPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [recommendations, setRecommendations] = useState(null);
  const [attention, setAttention] = useState(null);
  const [flags, setFlags] = useState([]);
  const [sector, setSector] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

  useEffect(() => {
    Promise.all([api("/portfolios"), api("/flags")])
      .then(([rows, flagRows]) => {
        setPortfolios(rows);
        setFlags(flagRows);
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
    Promise.all([
      api(`/portfolios/${portfolioId}/recommendations`),
      api(`/portfolios/${portfolioId}/attention`),
    ])
      .then(([ideas, moves]) => {
        if (!cancelled) {
          setRecommendations(ideas);
          setAttention(moves);
        }
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

  useEffect(() => {
    if (portfolioId) sessionStorage.setItem("finsight_portfolio", portfolioId);
  }, [portfolioId]);

  function flaggedSecurity(securityId) {
    return flags.some((flag) => flag.security_id === securityId);
  }

  function flaggedSector(name) {
    return flags.some((flag) => flag.target_type === "sector" && flag.sector?.toLowerCase() === name.toLowerCase());
  }

  async function addFlag(payload, success) {
    setToast("");
    try {
      const created = await api("/flags", { method: "POST", body: JSON.stringify(payload) });
      setFlags((current) => [created, ...current]);
      setToast(success);
    } catch (err) {
      setToast(err.message);
    }
  }

  async function removeFlag(flag) {
    setToast("");
    try {
      await api(`/flags/${flag.id}`, { method: "DELETE" });
      setFlags((current) => current.filter((item) => item.id !== flag.id));
      setToast("Flag removed");
    } catch (err) {
      setToast(err.message);
    }
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Research</p>
            <h1>Ideas and flags</h1>
            <p className="muted">Suggestions come from stored holdings and fundamentals. Flags are marks you keep.</p>
          </div>
          <label className="field">Portfolio
            <select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>
              {portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        </header>
        <ErrorState message={error} />
        <Toast message={toast} onDismiss={() => setToast("")} />
        {loading ? <Skeleton lines={6} label="Loading ideas" /> : null}
        {!loading && portfolios.length === 0 ? <EmptyState title="No portfolio yet">Create a portfolio before asking for ideas.</EmptyState> : null}
        {!loading && recommendations ? (
          <div className="stack">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Suggestions</h2>
                  <p className="muted">{recommendations.disclaimer}</p>
                </div>
              </div>
              {recommendations.items.length === 0 ? <EmptyState title="No unheld securities">Every active stored security is already in this portfolio.</EmptyState> : (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Security</th><th>Sector</th><th className="numeric"><LearnTerm slug="roe">ROE</LearnTerm></th><th className="numeric"><LearnTerm slug="pe-ratio">P/E</LearnTerm></th><th>Why it is listed</th></tr></thead>
                    <tbody>
                      {recommendations.items.map((row) => (
                        <tr key={row.security_id}>
                          <td><Link className="ticker-link" href={`/securities/${row.ticker}`}>{row.ticker}</Link><br /><span className="muted">{row.name}</span></td>
                          <td>{row.sector}</td>
                          <td className="numeric">{percent(row.roe)}</td>
                          <td className="numeric">{number(row.pe_ratio, { maximumFractionDigits: 2 })}</td>
                          <td>{row.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Doing badly today</h2>
                  <p className="muted">Negative day P/L from the current quote or the stored close. Flag a name or a sector to keep it.</p>
                </div>
              </div>
              {!attention?.stocks.length && !attention?.areas.length ? <EmptyState title="Nothing is down">No holding has a negative day move.</EmptyState> : (
                <div className="split-grid">
                  <div>
                    <h3>Stocks</h3>
                    {attention.stocks.length === 0 ? <p className="muted">No single holding is down.</p> : (
                      <ul className="plain-list">
                        {attention.stocks.map((row) => (
                          <li key={row.security_id}>
                            <strong>{row.ticker}</strong> {row.sector} · {money(row.day_pl)}
                            {flaggedSecurity(row.security_id) ? <span className="muted"> Flagged</span> : (
                              <button type="button" onClick={() => addFlag({ target_type: "security", security_id: row.security_id, note: "Negative day move" }, `${row.ticker} flagged`)}>Flag</button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <h3>Areas</h3>
                    {attention.areas.length === 0 ? <p className="muted">No sector total is down.</p> : (
                      <ul className="plain-list">
                        {attention.areas.map((row) => (
                          <li key={row.sector}>
                            <strong>{row.sector}</strong> · {money(row.day_pl)}
                            {flaggedSector(row.sector) ? <span className="muted"> Flagged</span> : (
                              <button type="button" onClick={() => addFlag({ target_type: "sector", sector: row.sector, note: "Sector day move is negative" }, `${row.sector} flagged`)}>Flag</button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
              <form className="row" onSubmit={(event) => {
                event.preventDefault();
                if (!sector.trim()) return;
                addFlag({ target_type: "sector", sector: sector.trim(), note: note.trim() || null }, `${sector.trim()} flagged`);
                setSector("");
                setNote("");
              }}>
                <label className="field">Flag a sector<input value={sector} maxLength={64} onChange={(event) => setSector(event.target.value)} placeholder="Healthcare" /></label>
                <label className="field">Note<input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Optional" /></label>
                <button className="primary" type="submit" disabled={!sector.trim()}>Flag sector</button>
              </form>
            </section>
            <section className="panel">
              <div className="panel-header"><h2>Your flags</h2><span className="muted">{flags.length}</span></div>
              {flags.length === 0 ? <EmptyState title="No flags yet">Flag a stock or sector from the list above.</EmptyState> : (
                <ul className="plain-list">
                  {flags.map((flag) => (
                    <li key={flag.id}>
                      <strong>{flag.target_type === "security" ? flag.ticker : flag.sector}</strong>
                      {flag.target_type === "security" ? <span className="muted"> {flag.sector}</span> : <span className="muted"> sector</span>}
                      {flag.note ? <span> · {flag.note}</span> : null}
                      <button type="button" onClick={() => removeFlag(flag)}>Remove</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        ) : null}
      </main>
    </>
  );
}
