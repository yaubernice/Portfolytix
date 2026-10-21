"use client";

import { roundFigures } from "../lib/figures";

const SOURCE_LABEL = {
  database: "Stored record",
  calculation: "Calculated in Portfolytix",
  provider: "Market data provider",
  unavailable: "Not available",
};

const HIDDEN_VALUES = new Set(["undefined", "unavailable", "insufficient_history"]);
const PLAIN_NUMBER = /^-?\d+(\.\d+)?$/;

function displayValue(value) {
  const text = String(value);
  if (PLAIN_NUMBER.test(text)) return roundFigures(text, 4, true);
  return text.replace(/-?\d+\.\d{5,}/g, (token) => roundFigures(token, 4, true));
}

export function answerOrigin(source) {
  if (source === "llm") return "Written by the configured model";
  if (source === "template") return "Restated from the evidence, without a language model";
  return "";
}

const TICKER_LINE = /^[A-Z][A-Z0-9.]{0,9}$/;
const ADVERSE_MARK = " (names a difficult event)";

export function AnswerText({ text, evidence = null, question = "", streaming = false }) {
  const shown = roundFigures(text, 4, !streaming);
  const brief = parseNewsBrief(shown);
  if (brief) {
    return <NewsBrief brief={brief} evidence={evidence} streaming={streaming} />;
  }
  const lines = splitSentences(shown);
  const caret = streaming ? <span className="generating-caret" aria-hidden="true" /> : null;
  return (
    <div className="answer-layout">
      <AnswerFigure evidence={evidence} question={question} text={shown} />
      {lines ? (
        <>
          <p className="answer-lead">{lines.lead}{lines.rest.length ? null : caret}</p>
          <ul className="answer-points">
            {lines.rest.map((line, index) => (
              <li key={line}>
                {line}
                {caret && index === lines.rest.length - 1 ? caret : null}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="answer-lead">{shown}{caret}</p>
      )}
    </div>
  );
}

function splitSentences(text) {
  const parts = text.split(/(?<=[.!?])\s+(?!\[[eE]\d+\])/).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  return { lead: parts[0], rest: parts.slice(1) };
}

const VISUAL_WORD = /\b(chart|charts|graph|graphs|graphic|graphics|visual|visuals|picture|plot|diagram|draw)\b/i;
const FORECAST_WORD = /\b(forecast|tomorrow|next month|next week|next year|price target|going to|will my|will the|will it)\b/i;

function visualKind(question, text) {
  const q = String(question || "");
  const forecast = FORECAST_WORD.test(q) || /no forecast is given/i.test(text);
  const wants = VISUAL_WORD.test(q);
  const day = /\b(today|day|gainer|loser|mover|drove)\b/i.test(q);
  const mix = /\b(allocation|weight|holding|holdings|position|positions|concentration|mix|overview|summarize|summary)\b/i.test(q);
  const history = /\b(over time|history|trend|line|performance|value)\b/i.test(q);
  if (forecast) return wants ? "now" : null;
  if (history && !day && (wants || /\bperformance\b/i.test(q))) return "line";
  if (wants && day) return "day";
  if (wants || mix) return "weights";
  if (day) return "day";
  return null;
}

const TILES = [
  [/return on equity|\broe\b/i, "weighted_roe", "percent"],
  [/sharpe/i, "sharpe_ratio", "number"],
  [/drawdown/i, "max_drawdown", "percent"],
  [/volatility|\brisk\b/i, "volatility", "percent"],
  [/unrealized|p\/l|p&l|profit and loss/i, "unrealized_pl", "money"],
  [/\breturn\b|how did/i, "total_return", "percent"],
];

function metricByName(evidence, name) {
  return (evidence?.metrics || []).find((row) => row.name === name && row.availability !== "unavailable" && !HIDDEN_VALUES.has(String(row.value)));
}

function formatMetric(value, kind) {
  const number = Number(value);
  if (!Number.isFinite(number)) return displayValue(value);
  if (kind === "percent") return roundFigures(`${number * 100}%`, 4, true);
  if (kind === "money") return `${number < 0 ? "-" : ""}$${roundFigures(String(Math.abs(number)), 4, true)}`;
  return roundFigures(String(number), 4, true);
}

function AnswerFigure({ evidence, question, text }) {
  if (/not in the stored evidence/i.test(text)) return null;
  const asked = question || evidence?.question || "";
  const kind = visualKind(asked, text);
  if (kind === "line") return <ValueLine chart={evidence?.chart} />;
  if (kind === "day" || kind === "weights" || kind === "now") {
    return <HoldingBars evidence={evidence} kind={kind === "day" ? "day" : "weights"} future={kind === "now"} />;
  }
  if (FORECAST_WORD.test(asked) || /no forecast is given/i.test(text)) return null;
  const tile = TILES.find(([pattern]) => pattern.test(asked));
  if (!tile) return null;
  const metric = metricByName(evidence, tile[1]);
  if (!metric) return null;
  return (
    <p className="answer-stat">
      <span>{metric.label || tile[1]}</span>
      <strong>{formatMetric(metric.value, tile[2])}</strong>
    </p>
  );
}

function HoldingBars({ evidence, kind, future }) {
  const prefix = kind === "day" ? "day_change:" : "weight:";
  const rows = (evidence?.metrics || [])
    .filter((row) => String(row.name).startsWith(prefix) && row.availability !== "unavailable")
    .map((row) => ({ ticker: row.name.split(":")[1], value: Number(row.value) }))
    .filter((row) => Number.isFinite(row.value))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 8);
  if (!rows.length) return null;
  const scale = Math.max(...rows.map((row) => Math.abs(row.value)), kind === "weights" ? 1 : 0.01);
  const caption = future
    ? "Current mix. No future chart is drawn."
    : kind === "day"
      ? "Delayed day change for each holding. A bar is not a forecast."
      : "Each bar is that holding's share of portfolio market value.";
  return (
    <figure className="answer-figure">
      {rows.map((row) => {
        const width = Math.min(Math.abs(row.value) / scale * 100, 100);
        const label = formatMetric(row.value, "percent");
        return (
          <div className="bar-row" key={row.ticker}>
            <span>{row.ticker}</span>
            <div className="weight-track" role="img" aria-label={`${row.ticker} ${label}`}>
              <div className={row.value < 0 ? "weight-fill negative" : "weight-fill"} style={{ width: `${width}%` }} />
            </div>
            <span>{label}</span>
          </div>
        );
      })}
      <figcaption className="muted">{caption}</figcaption>
    </figure>
  );
}

function ValueLine({ chart }) {
  const points = (chart || []).map((row) => ({ date: row.date, value: Number(row.value) })).filter((row) => Number.isFinite(row.value));
  if (points.length < 2) {
    return <p className="muted news-caveat">A line needs at least two stored portfolio values. No future line is drawn.</p>;
  }
  const values = points.map((row) => row.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 640;
  const height = 140;
  const padX = 8;
  const padY = 12;
  const polyline = points.map((row, index) => {
    const x = padX + (index / (points.length - 1)) * (width - padX * 2);
    const y = padY + (1 - (row.value - min) / span) * (height - padY * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <figure className="answer-figure">
      <svg className="answer-line" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Stored portfolio value from ${points[0].date} to ${points[points.length - 1].date}`}>
        <polyline fill="none" stroke="currentColor" strokeWidth="2" points={polyline} />
      </svg>
      <figcaption className="muted">Stored portfolio value from {points[0].date} to {points[points.length - 1].date}. This line is not a forecast.</figcaption>
    </figure>
  );
}

function parseNewsBrief(text) {
  const lead = [];
  const holdings = [];
  const notes = [];
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (TICKER_LINE.test(line)) {
      current = { ticker: line, headlines: [] };
      holdings.push(current);
      continue;
    }
    if (current && line.startsWith("- ")) {
      const adverse = line.endsWith(ADVERSE_MARK);
      const body = (adverse ? line.slice(0, -ADVERSE_MARK.length) : line).replace(/^- /, "");
      current.headlines.push({ text: body, adverse });
      continue;
    }
    if (current) notes.push(line);
    else lead.push(line);
  }
  if (!holdings.length) return null;
  return { lead, holdings, notes };
}

function weightOf(evidence, ticker) {
  const item = (evidence?.metrics || []).find((row) => row.name === `weight:${ticker}`);
  if (!item || item.availability === "unavailable") return null;
  const value = Number(item.value);
  if (!Number.isFinite(value) || value < 0) return null;
  return value;
}

function NewsBrief({ brief, evidence, streaming }) {
  const adverse = brief.holdings.some((holding) => holding.headlines.some((row) => row.adverse));
  const weights = brief.holdings.map((holding) => weightOf(evidence, holding.ticker));
  const hasWeight = weights.some((value) => value != null);
  return (
    <div className="news-brief">
      {brief.lead[0] ? (
        <p className={adverse ? "news-status adverse" : "news-status"}>{brief.lead[0]}</p>
      ) : null}
      {brief.lead.slice(1).map((line) => <p key={line} className="muted news-caveat">{line}</p>)}
      <div className="news-holdings">
        {brief.holdings.map((holding, index) => {
          const weight = weights[index];
          const label = weight == null ? "" : roundFigures(`${weight * 100}%`, 4, true);
          return (
            <article className="news-card" key={holding.ticker}>
              <header>
                <h3>{holding.ticker}</h3>
                {label ? <span>{label}</span> : null}
              </header>
              {weight != null ? (
                <div
                  className="weight-track"
                  role="img"
                  aria-label={`${holding.ticker} is ${label} of portfolio market value`}
                >
                  <div className="weight-fill" style={{ width: `${Math.min(weight * 100, 100)}%` }} />
                </div>
              ) : null}
              <ul>
                {holding.headlines.map((row) => (
                  <li key={row.text} className={row.adverse ? "adverse" : undefined}>{row.text}</li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
      {hasWeight ? <p className="muted news-caveat">Each bar is that holding&apos;s share of portfolio market value.</p> : null}
      {brief.notes.map((line) => <p key={line} className="news-note">{line}</p>)}
      {streaming ? <span className="generating-caret" aria-hidden="true" /> : null}
    </div>
  );
}

export function EvidenceList({ facts = [], metrics = [] }) {
  const items = [...facts, ...metrics];
  if (!items.length) return null;
  return (
    <div className="evidence-list">
      {items.map((item) => {
        const exact = String(item.value);
        const missing = item.availability === "unavailable" || HIDDEN_VALUES.has(exact);
        const shown = missing ? "—" : displayValue(exact);
        return (
          <details className="evidence-item" key={item.id || `${item.kind}-${item.name}`}>
            <summary>
              <span>{item.label || item.name}</span>
              <strong>{shown}{!missing && item.unit ? ` ${item.unit}` : ""}</strong>
            </summary>
            {!missing && shown !== exact ? <p>Exact value {exact}{item.unit ? ` ${item.unit}` : ""}</p> : null}
            {item.method ? <p>{item.method}</p> : null}
            {item.as_of ? <p>As of {item.as_of}</p> : null}
            <p className="muted">
              {SOURCE_LABEL[item.source] || item.source}
              {item.id ? ` · Reference ${item.id}` : ""}
            </p>
          </details>
        );
      })}
    </div>
  );
}
