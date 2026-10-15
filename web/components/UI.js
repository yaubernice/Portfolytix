"use client";

import { useEffect } from "react";

export function money(value, currency = "USD") {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(number);
}

export function number(value, options = {}) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return new Intl.NumberFormat("en-US", options).format(parsed);
}

export function percent(value, options = {}) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 2,
    ...options,
  }).format(parsed);
}

export function dateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

export function StatusBadge({ value = "unknown" }) {
  const normalized = String(value).toLowerCase();
  const tone = ["ok", "success", "completed", "fresh", "connected", "realtime"].includes(normalized)
    ? "positive"
    : ["failed", "error", "stale", "unavailable"].includes(normalized)
      ? "negative"
      : "neutral";
  return <span className={`status status-${tone}`}>{String(value).replaceAll("_", " ")}</span>;
}

export function Skeleton({ lines = 3, label = "Loading" }) {
  return (
    <div className="skeleton-stack" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, index) => (
        <span className="skeleton" key={index} />
      ))}
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="state-card">
      <strong>{title}</strong>
      {children ? <p className="muted">{children}</p> : null}
    </div>
  );
}

export function ErrorState({ message, retry }) {
  if (!message) return null;
  return (
    <div className="state-card state-error" role="alert">
      <strong>Unable to load data</strong>
      <p>{message}</p>
      {retry ? <button type="button" onClick={retry}>Try again</button> : null}
    </div>
  );
}

export function KpiCard({ label, value, detail, tone = "" }) {
  return (
    <article className="kpi-card">
      <p className="kpi-label">{label}</p>
      <p className={`kpi-value ${tone}`}>{value}</p>
      {detail ? <p className="kpi-detail">{detail}</p> : null}
    </article>
  );
}

export function Pagination({ offset, limit, total, onChange, disabled = false }) {
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + limit, total);
  return (
    <div className="pagination" aria-label="Pagination">
      <span className="muted">{start}–{end} of {total}</span>
      <div className="row">
        <button type="button" disabled={disabled || offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </button>
        <button type="button" disabled={disabled || offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Next
        </button>
      </div>
    </div>
  );
}

export function Toast({ message, tone = "success", onDismiss }) {
  useEffect(() => {
    if (!message || !onDismiss) return undefined;
    const timer = setTimeout(onDismiss, 3500);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);
  if (!message) return null;
  return (
    <div className={`toast toast-${tone}`} role="status">
      <span>{message}</span>
      <button type="button" aria-label="Dismiss notification" onClick={onDismiss}>×</button>
    </div>
  );
}

export function LineChart({ values = [], label = "Trend" }) {
  const points = values.map(Number).filter(Number.isFinite);
  if (points.length < 2) return <EmptyState title="No chart data">More observations are required.</EmptyState>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const polyline = points.map((value, index) => {
    const x = (index / (points.length - 1)) * 100;
    const y = 100 - ((value - min) / span) * 100;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg className="chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={label}>
      <polyline fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" points={polyline} />
    </svg>
  );
}

export function TimeSeriesChart({
  points = [],
  valueKey,
  label,
  format = number,
  tone = "",
}) {
  const rows = points.filter((point) => point[valueKey] !== null && point[valueKey] !== undefined);
  const values = rows.map((point) => point[valueKey]);
  return (
    <div className={`time-series ${tone}`}>
      <LineChart values={values} label={label} />
      {rows.length ? (
        <div className="chart-range" aria-hidden="true">
          <span>{rows[0].date}</span>
          <strong>{format(rows[rows.length - 1][valueKey])}</strong>
          <span>{rows[rows.length - 1].date}</span>
        </div>
      ) : null}
      <details className="chart-data">
        <summary>View chart data</summary>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th className="numeric">{label}</th></tr></thead>
            <tbody>{rows.map((point) => (
              <tr key={`${valueKey}-${point.date}`}>
                <td>{point.date}</td><td className="numeric">{format(point[valueKey])}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function AllocationChart({ rows = [] }) {
  if (!rows.length) return <EmptyState title="No allocation data">Position values are required.</EmptyState>;
  return (
    <div className="allocation-chart" role="img" aria-label="Portfolio allocation">
      {rows.map((row) => (
        <div className="allocation-row" key={row.ticker}>
          <div><strong>{row.ticker}</strong><span>{percent(row.weight)}</span></div>
          <span className="allocation-track" aria-hidden="true">
            <span style={{ width: `${Math.max(0, Math.min(100, Number(row.weight) * 100))}%` }} />
          </span>
          <small className="muted">{money(row.market_value)}</small>
        </div>
      ))}
      <details className="chart-data">
        <summary>View allocation data</summary>
        <div className="table-wrap"><table>
          <thead><tr><th>Ticker</th><th className="numeric">Value</th><th className="numeric">Weight</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={`allocation-${row.ticker}`}><td>{row.ticker}</td><td className="numeric">{money(row.market_value)}</td><td className="numeric">{percent(row.weight)}</td></tr>)}</tbody>
        </table></div>
      </details>
    </div>
  );
}
