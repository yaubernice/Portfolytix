"use client";

import { useEffect, useRef, useState } from "react";

export function isMissing(value) {
  return value === null || value === undefined || value === "";
}

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
  const labels = {
    realtime: "Real-time",
    live: "Real-time",
    delayed: "Delayed",
    historical: "Historical",
    simulated: "Simulated",
    stale: "Stale",
    unavailable: "Unavailable",
  };
  return <span className={`status status-${tone}`}>{labels[normalized] || String(value).replaceAll("_", " ")}</span>;
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

export function AttentionMark() {
  return <span className="attention-mark" role="img" aria-label="This figure is down">!</span>;
}

function logoSymbol(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!/^[A-Z0-9.-]{1,16}$/.test(symbol)) return "";
  return symbol.replaceAll(".", "-");
}

export function CompanyLogo({ ticker, size = 28 }) {
  const symbol = logoSymbol(ticker);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [symbol]);
  const letters = String(ticker || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?";
  const style = { "--logo-size": `${size}px` };
  if (!symbol || failed) {
    return <span className="company-logo company-logo-fallback" style={style} aria-hidden="true">{letters}</span>;
  }
  return (
    <img
      className="company-logo"
      style={style}
      src={`https://assets.parqet.com/logos/symbol/${encodeURIComponent(symbol)}`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function TickerIdentity({ ticker, name, size = 28 }) {
  return (
    <span className="ticker-identity">
      <CompanyLogo ticker={ticker} size={size} />
      <span className="ticker-copy">
        {ticker ? <strong>{ticker}</strong> : null}
        {name ? <span className="muted">{name}</span> : null}
      </span>
    </span>
  );
}

export function KpiCard({ label, value, detail, tone = "", alert = false }) {
  return (
    <article className="kpi-card">
      <p className="kpi-label">{label}</p>
      <p className={`kpi-value ${tone}`}>{alert ? <AttentionMark /> : null}{value}</p>
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
  const width = 640;
  const height = 168;
  const padX = 12;
  const padY = 18;
  const polyline = points.map((value, index) => {
    const x = padX + (index / (points.length - 1)) * (width - padX * 2);
    const y = padY + (1 - (value - min) / span) * (height - padY * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <line x1={padX} x2={width - padX} y1={height - padY} y2={height - padY} stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      <polyline fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" points={polyline} />
    </svg>
  );
}

export function InteractiveChart({ rows = [], label = "Chart", formatValue = number, tone = "" }) {
  const frame = useRef(null);
  const [index, setIndex] = useState(null);
  const points = rows.filter((row) => Number.isFinite(Number(row.value)));
  if (points.length < 2) {
    const only = points[0];
    return <p className="compact-note">{only ? `${only.date}: ${formatValue(only.value)}. One observation is not enough to draw a line.` : "More observations are required before this chart can be drawn."}</p>;
  }
  const values = points.map((row) => Number(row.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 640;
  const height = 180;
  const padX = 10;
  const padY = 16;
  const coords = points.map((row, pointIndex) => ({
    x: padX + (pointIndex / (points.length - 1)) * (width - padX * 2),
    y: padY + (1 - (Number(row.value) - min) / span) * (height - padY * 2),
  }));
  const polyline = coords.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  const active = index == null ? null : points[index];
  const marker = index == null ? null : coords[index];

  function pick(clientX) {
    const rect = frame.current?.getBoundingClientRect();
    if (!rect?.width) return;
    const x = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    let distance = Infinity;
    coords.forEach((point, pointIndex) => {
      const gap = Math.abs(point.x - x);
      if (gap < distance) {
        distance = gap;
        best = pointIndex;
      }
    });
    setIndex(best);
  }

  return (
    <div className={`plot ${tone}`}>
      <div className="plot-scale" aria-hidden="true">
        <span>{formatValue(max)}</span>
        <span>{formatValue(min)}</span>
      </div>
      <div className="plot-main">
      <div
        className="plot-frame"
        ref={frame}
        tabIndex={0}
        role="group"
        aria-label={`${label}. Arrow keys read each point.`}
        onMouseMove={(event) => pick(event.clientX)}
        onMouseLeave={() => setIndex(null)}
        onFocus={() => setIndex((current) => current ?? points.length - 1)}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            setIndex((current) => Math.min(points.length - 1, (current ?? -1) + 1));
          }
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            setIndex((current) => Math.max(0, (current ?? points.length) - 1));
          }
          if (event.key === "Escape") setIndex(null);
        }}
      >
        <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
          <line x1={padX} x2={width - padX} y1={height - padY} y2={height - padY} stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          <polyline fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" points={polyline} />
          {marker ? <line x1={marker.x} x2={marker.x} y1={padY} y2={height - padY} stroke="currentColor" strokeOpacity="0.45" strokeWidth="1" vectorEffect="non-scaling-stroke" /> : null}
        </svg>
        {active ? (
          <p className="plot-tip" style={{ left: `${(marker.x / width) * 100}%` }}>
            <span>{active.date}</span>
            <strong>{formatValue(active.value)}</strong>
          </p>
        ) : null}
        <p className="sr-only" aria-live="polite">{active ? `${label}, ${active.date}, ${formatValue(active.value)}` : ""}</p>
      </div>
      <div className="chart-range" aria-hidden="true">
        <span>{points[0].date}</span>
        <span>{points[points.length - 1].date}</span>
      </div>
      {active ? null : <p className="plot-hint">Hover, or focus and use the arrow keys, to read a date and value.</p>}
    </div>
    </div>
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
  return (
    <div className={`time-series ${tone}`}>
      <InteractiveChart rows={rows.map((point) => ({ date: point.date, value: point[valueKey] }))} label={label} formatValue={format} tone={tone} />
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
      {rows.map((row) => {
        const weight = Math.max(0, Math.min(100, Number(row.weight) * 100));
        return (
          <div className="allocation-row" key={row.ticker}>
            <TickerIdentity ticker={row.ticker} size={22} />
            <span className="allocation-weight">{percent(row.weight)}</span>
            <span className="allocation-track" aria-hidden="true">
              <span style={{ width: `${weight}%`, minWidth: weight > 0 ? 3 : 0 }} />
            </span>
            <span className="allocation-value">{money(row.market_value)}</span>
          </div>
        );
      })}
      <details className="chart-data">
        <summary>View allocation data</summary>
        <div className="table-wrap"><table>
          <thead><tr><th>Ticker</th><th className="numeric">Value</th><th className="numeric">Weight</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={`allocation-${row.ticker}`}><td><TickerIdentity ticker={row.ticker} size={22} /></td><td className="numeric">{money(row.market_value)}</td><td className="numeric">{percent(row.weight)}</td></tr>)}</tbody>
        </table></div>
      </details>
    </div>
  );
}
