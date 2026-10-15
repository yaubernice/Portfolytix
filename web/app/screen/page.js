"use client";

import { useState } from "react";
import Link from "next/link";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, number, Pagination, percent, Skeleton } from "../../components/UI";
import { api } from "../../lib/api";

const RANGE_FILTERS = [
  ["roe", "ROE"], ["pe", "P/E"], ["revenue_growth", "Revenue growth"],
  ["market_cap", "Market cap (USD)"], ["eps", "EPS"], ["revenue", "Revenue"],
  ["profit_margin", "Profit margin"], ["dividend_yield", "Dividend yield"],
  ["beta", "Beta"], ["ebitda", "EBITDA"], ["price_to_book", "Price / book"],
  ["price_to_sales", "Price / sales"], ["roa", "ROA"], ["earnings_growth", "Earnings growth"],
];

const EMPTY_FILTERS = Object.fromEntries(RANGE_FILTERS.flatMap(([key]) => [[`${key}_min`, ""], [`${key}_max`, ""]]));
const RATIO_FIELDS = new Set(["roe", "revenue_growth", "profit_margin", "dividend_yield", "roa", "earnings_growth"]);

function appliedSummary(applied) {
  if (!applied) return [];
  const lines = [];
  for (const key of ["sector", "industry", "exchange"]) {
    if (applied[key]) lines.push(`${key} ${applied[key]}`);
  }
  for (const [key, value] of Object.entries(applied)) {
    const match = key.match(/^(.*)_(min|max)$/);
    if (!match || value === null || value === undefined || value === "") continue;
    const [, name, bound] = match;
    const shown = RATIO_FIELDS.has(name)
      ? percent(value)
      : name === "market_cap"
        ? number(value, { notation: "compact", maximumFractionDigits: 1 })
        : number(value, { maximumFractionDigits: 2 });
    lines.push(`${name.replaceAll("_", " ")} ${bound} ${shown}`);
  }
  return lines;
}

export default function ScreenPage() {
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, sector: "", industry: "", exchange: "" });
  const [sortBy, setSortBy] = useState("ticker");
  const [sortDirection, setSortDirection] = useState("asc");
  const [limit, setLimit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [applied, setApplied] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [naturalQuery, setNaturalQuery] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [parser, setParser] = useState("");
  const [lastMode, setLastMode] = useState("structured");

  async function runScreen(nextOffset = 0, natural = false) {
    setError("");
    setLoading(true);
    try {
      const criteria = Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, value.trim() || null]));
      const payload = natural
        ? { query: naturalQuery.trim(), sort_by: sortBy, sort_direction: sortDirection, limit, offset: nextOffset }
        : { ...criteria, sort_by: sortBy, sort_direction: sortDirection, limit, offset: nextOffset };
      const body = await api(natural ? "/screen/natural" : "/screen", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setApplied(body.applied);
      setRows(body.items);
      setTotal(body.total);
      setOffset(body.offset);
      setDisclaimer(body.disclaimer);
      setParser(body.parser || "");
      setLastMode(natural ? "natural" : "structured");
    } catch (err) {
      setError(err.message);
      setRows([]);
      setTotal(0);
      setApplied(null);
      setDisclaimer("");
      setParser("");
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Research</p><h1>Security screening</h1><p className="muted">Filter stored fundamentals with backend-supported criteria.</p></div></header>
        <section className="panel">
          <div className="panel-header"><h2>Structured filters</h2><button type="button" onClick={() => setFilters({ ...EMPTY_FILTERS, sector: "", industry: "", exchange: "" })}>Clear</button></div>
          <form onSubmit={(event) => { event.preventDefault(); runScreen(0); }}>
            <div className="filter-grid">
              {["sector", "industry", "exchange"].map((key) => <label className="field" key={key}>{key[0].toUpperCase() + key.slice(1)}<input value={filters[key]} onChange={(event) => updateFilter(key, event.target.value)} /></label>)}
              {RANGE_FILTERS.map(([key, label]) => (
                <div className="field" key={key}><span>{label}</span><div className="row">
                  <input aria-label={`${label} minimum`} inputMode="decimal" placeholder="Min" value={filters[`${key}_min`]} onChange={(event) => updateFilter(`${key}_min`, event.target.value)} />
                  <input aria-label={`${label} maximum`} inputMode="decimal" placeholder="Max" value={filters[`${key}_max`]} onChange={(event) => updateFilter(`${key}_max`, event.target.value)} />
                </div></div>
              ))}
            </div>
            <div className="row">
              <label className="field">Sort by<select value={sortBy} onChange={(event) => setSortBy(event.target.value)}><option value="ticker">Ticker</option><option value="roe">ROE</option><option value="pe_ratio">P/E</option><option value="revenue_growth">Revenue growth</option><option value="market_cap">Market cap</option></select></label>
              <label className="field">Direction<select value={sortDirection} onChange={(event) => setSortDirection(event.target.value)}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
              <label className="field">Rows<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option>10</option><option>20</option><option>50</option><option>100</option></select></label>
              <button className="primary" type="submit" disabled={loading}>Run screen</button>
            </div>
          </form>
        </section>
        <section className="panel">
          <div className="panel-header"><div><h2>Natural-language screen</h2><p className="muted">The assistant converts your request into the same validated filters.</p></div></div>
          <form onSubmit={(event) => { event.preventDefault(); runScreen(0, true); }}>
            <label className="field">Screen request<textarea rows={2} maxLength={500} value={naturalQuery} onChange={(event) => setNaturalQuery(event.target.value)} placeholder="Technology companies with ROE above 40% and P/E below 30" /></label>
            <button type="submit" disabled={loading || !naturalQuery.trim()}>Parse and screen</button>
            <p className="muted">The sentence goes to the configured model, which returns filters. Results show those filters and whether a model produced them. In the seeded universe, technology is AAPL, MSFT, and NVDA, and only NVDA has ROE above 40%.</p>
          </form>
        </section>
        <ErrorState message={error} />
        <section className="panel" aria-live="polite">
          <div className="panel-header"><div><h2>Results</h2><p className="muted">{total} matching securities</p></div>{applied ? <span className="status">{appliedSummary(applied).length} filters</span> : null}</div>
          {appliedSummary(applied).length ? <p className="muted">Understood{parser ? ` by ${parser}` : ""}: {appliedSummary(applied).join(", ")}.</p> : null}
          {lastMode === "natural" && applied && /\d/.test(naturalQuery) && !appliedSummary(applied).some((item) => item.includes("min") || item.includes("max")) ? <p className="muted">A number was in the question, and no minimum or maximum was applied.</p> : null}
          {loading ? <Skeleton lines={6} label="Running screen" /> : null}
          {!loading && !rows.length ? <EmptyState title="No screening results">Set filters and run the screen, or broaden your criteria.</EmptyState> : null}
          {!loading && rows.length ? <>
            <div className="table-wrap"><table><thead><tr><th>Security</th><th>Sector</th><th className="numeric"><LearnTerm slug="roe">ROE</LearnTerm></th><th className="numeric"><LearnTerm slug="pe-ratio">P/E</LearnTerm></th><th className="numeric">Growth</th><th className="numeric">Market cap</th><th>As of</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.security_id}><td><Link className="ticker-link" href={`/securities/${row.ticker}`}>{row.ticker}</Link><br /><span className="muted">{row.name}</span></td><td>{row.sector}</td><td className="numeric">{percent(row.roe)}</td><td className="numeric">{number(row.pe_ratio, { maximumFractionDigits: 2 })}</td><td className="numeric">{percent(row.revenue_growth)}</td><td className="numeric">{number(row.market_cap, { notation: "compact", maximumFractionDigits: 1 })}</td><td>{row.as_of}</td></tr>)}</tbody>
            </table></div>
            <Pagination offset={offset} limit={limit} total={total} disabled={loading} onChange={(nextOffset) => runScreen(nextOffset, lastMode === "natural")} />
          </> : null}
          {disclaimer ? <p className="muted">{disclaimer}</p> : null}
        </section>
      </main>
    </>
  );
}
