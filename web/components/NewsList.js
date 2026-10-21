"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import GeneratingStatus, { NEWS_PHASES } from "./GeneratingStatus";
import { api } from "../lib/api";
import { roundFigures } from "../lib/figures";
import { CompanyLogo } from "./UI";

function publishedLabel(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function briefLabel(item) {
  if (item.brief_source === "llm") return "Written by the configured model. ";
  if (item.brief_source === "stored" && !/^No summary is stored/i.test(item.brief || "")) {
    return "From the stored story text. ";
  }
  return "";
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

export function namedInHeadline(item) {
  const headline = ` ${String(item.headline || "").toUpperCase()} `;
  return [...new Set((item.tickers || []).map((ticker) => String(ticker).toUpperCase()).filter((ticker) => {
    if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker)) return false;
    const pattern = new RegExp(`(^|[^A-Z0-9])${ticker.replaceAll(".", "\\.")}([^A-Z0-9]|$)`);
    return pattern.test(headline);
  }))];
}

export function storyScope(item, held, watched) {
  const named = namedInHeadline(item);
  const heldSet = new Set(held);
  const watchSet = new Set(watched);
  const related = [...new Set((item.tickers || []).map((ticker) => String(ticker).toUpperCase()))];
  const subject = named.length ? named : related;
  if (subject.some((ticker) => heldSet.has(ticker))) return "holdings";
  if (subject.some((ticker) => watchSet.has(ticker))) return "watchlist";
  if (subject.length) return "market";
  return "";
}

function relevance(item, held, watched) {
  if (!held.length && !watched.length) return "";
  const named = namedInHeadline(item);
  const heldSet = new Set(held);
  const watchSet = new Set(watched);
  const inHeld = named.filter((ticker) => heldSet.has(ticker));
  if (inHeld.length) return `About ${inHeld.slice(0, 3).join(", ")}, named in the headline.`;
  const inWatch = named.filter((ticker) => watchSet.has(ticker));
  if (inWatch.length) return `About ${inWatch.slice(0, 3).join(", ")} on your watchlist.`;
  const outside = named.filter((ticker) => !heldSet.has(ticker) && !watchSet.has(ticker));
  if (outside.length) return `About ${outside.slice(0, 3).join(", ")}, outside this portfolio.`;
  const related = [...new Set((item.tickers || []).map((ticker) => String(ticker).toUpperCase()))].filter((ticker) => heldSet.has(ticker) || watchSet.has(ticker));
  if (related.length) return `The provider related this story to ${related.slice(0, 3).join(", ")}. The headline does not name that symbol.`;
  return "";
}

function TickerMarks({ tickers }) {
  if (!tickers?.length) return null;
  const shown = tickers.slice(0, 4);
  const extra = tickers.length - shown.length;
  return (
    <span className="news-tickers">
      {shown.map((ticker) => (
        <span className="news-ticker" key={ticker}>
          <CompanyLogo ticker={ticker} size={18} />
          {ticker}
        </span>
      ))}
      {extra > 0 ? <span className="muted">+{extra}</span> : null}
    </span>
  );
}

function StoryImage({ src }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    <span className="news-media">
      <img src={src} alt="" onError={() => setFailed(true)} />
    </span>
  );
}

export default function NewsList({ items, provider, held = [], watched = [] }) {
  const [open, setOpen] = useState(null);
  const [reading, setReading] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setOpen(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (!open?.url) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    setReading(null);
    api("/news/read", {
      method: "POST",
      body: JSON.stringify({ url: open.url, headline: open.headline }),
    })
      .then((body) => {
        if (!cancelled) setReading(body);
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
  }, [open]);

  if (!items?.length) return null;
  const original = open ? safeUrl(open.url) : "";
  return (
    <>
      <ol className="news-feed">
        {items.map((item) => (
          <li key={`${item.url}-${item.headline}`}>
            <button type="button" className="news-story" onClick={() => setOpen(item)}>
              <StoryImage src={item.image_url} />
              <span className="news-copy">
                <span className="news-meta">{item.source} · {publishedLabel(item.published_at)}</span>
                <h3>{item.headline}</h3>
                {item.brief ? <span className="news-brief-line">{briefLabel(item)}{item.brief}</span> : null}
                <span className="news-relevance">{relevance(item, held, watched)}</span>
                <TickerMarks tickers={namedInHeadline(item)} />
                <span className="muted news-note">{item.provider || provider || "Provider unavailable"} · Open for a generated summary</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {open ? (
        <div className="explain-backdrop" onClick={() => setOpen(null)}>
          <section
            className="explain-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="news-read-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="explain-head">
              <div>
                <p className="eyebrow">{open.source || "Story"} · {publishedLabel(open.published_at)}</p>
                <h2 id="news-read-title">{open.headline}</h2>
              </div>
              <button type="button" onClick={() => setOpen(null)}>Close</button>
            </div>
            <p className="news-relevance">{relevance(open, held, watched)}</p>
            <p className="news-links">
              {namedInHeadline(open).slice(0, 4).map((ticker) => (
                <Link key={ticker} href={`/securities/${ticker}`}>{ticker} research</Link>
              ))}
              {original ? <a href={original} target="_blank" rel="noreferrer">Original article</a> : <span className="muted">No original link was provided.</span>}
            </p>
            {loading ? <GeneratingStatus phases={NEWS_PHASES} /> : null}
            {error ? <p className="error">{error}</p> : null}
            {reading ? (
              <>
                <p className="summary-label">{reading.source === "model" ? "Generated summary, from the language model" : "Generated summary, from the article text"}</p>
                <dl className="explain-points">
                  <div>
                    <dt>What it is about</dt>
                    <dd>{roundFigures(reading.about)}</dd>
                  </div>
                  {reading.points?.length ? (
                    <div>
                      <dt>Key points</dt>
                      <dd>
                        <ul className="news-points">
                          {reading.points.map((point) => <li key={point}>{roundFigures(point)}</li>)}
                        </ul>
                      </dd>
                    </div>
                  ) : null}
                </dl>
                <p className="muted explain-note">{reading.note} This summary is not the publisher&apos;s article.</p>
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}
