"use client";

import { useState } from "react";
import Link from "next/link";
import GeneratingStatus, { SCREEN_PHASES } from "../../components/GeneratingStatus";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, number, Pagination, percent, Skeleton, TickerIdentity } from "../../components/UI";
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

const PARSER_LABEL = { rules: "the built-in parser", llm: "the configured model" };

function appliedSummary(applied) {
  if (!applied) return [];
  const lines = [];
  for (const key of ["sector", "industry", "exchange", "asset_type", "search"]) {
    if (applied[key]) lines.push(`${key.replaceAll("_", " ")} ${applied[key]}`);
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
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, sector: "", industry: "", exchange: "", asset_type: "", search: "" });
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
  const [note, setNote] = useState("");
  const [noteSource, setNoteSource] = useState("");
  const [lastMode, setLastMode] = useState("structured");
  const [busyMode, setBusyMode] = useState("");

  async function runScreen(nextOffset = 0, natural = false) {
    setError("");
    setLoading(true);
    setBusyMode(natural ? "natural" : "structured");
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
      if (natural && nextOffset === 0) {
        setNote(body.note || "");
        setNoteSource(body.note_source || "");
      }
      if (!natural) {
        setNote("");
        setNoteSource("");
      }
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
      setBusyMode("");
    }
  }

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Research</p><h1>Security screening</h1><p className="muted">Filter stored securities. A ratio only matches a company that has that figure stored.</p></div></header>
        <section className="panel">
          <div className="panel-header"><h2>Structured filters</h2><button type="button" onClick={() => setFilters({ ...EMPTY_FILTERS, sector: "", industry: "", exchange: "", asset_type: "", search: "" })}>Clear</button></div>
          <form onSubmit={(event) => { event.preventDefault(); runScreen(0); }}>
            <div className="filter-grid">
              {["sector", "industry", "exchange"].map((key) => <label className="field" key={key}>{key[0].toUpperCase() + key.slice(1)}<input value={filters[key]} onChange={(event) => updateFilter(key, event.target.value)} /></label>)}
              <label className="field">Asset type<select value={filters.asset_type} onChange={(event) => updateFilter("asset_type", event.target.value)}><option value="">Any</option><option value="equity">Equity</option><option value="etf">ETF</option><option value="fund">Fund</option><option value="index">Index</option><option value="other">Other</option></select></label>
              <label className="field">Ticker or name<input value={filters.search} onChange={(event) => updateFilter("search", event.target.value)} placeholder="VOO or Hang Seng" /></label>
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
            <p className="muted">A sector, ETF, fund, place, or name in the sentence is applied directly. Chinese companies and Hong Kong match stored names, and a fund that excludes China is left out. The configured model then writes a short note about the stored names on this page. It cannot add a company, a sector, or a number the screen did not return. A ratio such as ROE only matches securities that have that figure stored.</p>
          </form>
        </section>
        <ErrorState message={error} />
        <section className="panel" aria-live="polite">
          <div className="panel-header"><div><h2>Results</h2><p className="muted">{total} matching securities</p></div>{applied ? <span className="status">{appliedSummary(applied).length} filters</span> : null}</div>
          {appliedSummary(applied).length ? <p className="muted">Understood{parser ? ` by ${PARSER_LABEL[parser] || parser}` : ""}: {appliedSummary(applied).join(", ")}.</p> : null}
          {note ? <p className="compact-note">{noteSource === "llm" ? "Written by the configured model. " : "Restated from the stored results. "}{note}</p> : null}
          {applied?.asset_type === "etf" && !applied?.search && total > limit ? <p className="muted">These are stored ETFs, sorted by ticker. Type a ticker or name, such as VOO or Hang Seng, to jump to one product. A Hang Seng product appears when its stored name matches; there is no separate Hang Seng index listing.</p> : null}
          {applied?.sector && total <= limit ? <p className="muted">These are the active securities stored with this sector. Most imported listings have no sector, so a sector request cannot include them. Type a ticker or a name to find one of those.</p> : null}
          {lastMode === "natural" && applied && /\d/.test(naturalQuery) && !appliedSummary(applied).some((item) => item.includes("min") || item.includes("max")) ? <p className="muted">A number was in the question, and no minimum or maximum was applied.</p> : null}
          {loading && busyMode === "natural" ? <GeneratingStatus phases={SCREEN_PHASES} /> : null}
          {loading && busyMode !== "natural" ? <Skeleton lines={6} label="Running screen" /> : null}
          {!loading && !rows.length ? <EmptyState title="No screening results">Set filters and run the screen, or broaden your criteria.</EmptyState> : null}
          {!loading && rows.length ? <>
            <div className="table-wrap"><table><thead><tr><th>Security</th><th>Type</th><th>Sector</th><th className="numeric"><LearnTerm slug="roe">ROE</LearnTerm></th><th className="numeric"><LearnTerm slug="pe-ratio">P/E</LearnTerm></th><th className="numeric">Growth</th><th className="numeric">Market cap</th><th>As of</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.security_id}><td><Link className="ticker-link" href={`/securities/${row.ticker}`}><TickerIdentity ticker={row.ticker} name={row.name} /></Link></td><td>{row.asset_type || "—"}</td><td>{row.sector || "—"}</td><td className="numeric">{percent(row.roe)}</td><td className="numeric">{number(row.pe_ratio, { maximumFractionDigits: 2 })}</td><td className="numeric">{percent(row.revenue_growth)}</td><td className="numeric">{number(row.market_cap, { notation: "compact", maximumFractionDigits: 1 })}</td><td>{row.as_of || "—"}</td></tr>)}</tbody>
            </table></div>
            <Pagination offset={offset} limit={limit} total={total} disabled={loading} onChange={(nextOffset) => runScreen(nextOffset, lastMode === "natural")} />
          </> : null}
          {!loading && rows.some((row) => row.roe == null) ? <p className="muted">A dash means no fundamental snapshot is stored for that security. The missing ratio is omitted, not treated as zero.</p> : null}
          {disclaimer ? <p className="muted">{disclaimer}</p> : null}
        </section>
      </main>
    </>
  );
}
