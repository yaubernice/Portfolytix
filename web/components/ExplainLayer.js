"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import GeneratingStatus, { EXPLAIN_PHASES } from "./GeneratingStatus";
import { roundFigures } from "../lib/figures";
import { api } from "../lib/api";

const PORTFOLIO_KEY = "finsight_portfolio";

function explainOrigin(source) {
  if (source === "model") return "Written by the configured model. The figures below stay the ones calculated for this portfolio.";
  if (source === "glossary") return "From the glossary. The figures are calculated for this portfolio.";
  if (source === "security") return "From the stored company record.";
  if (source === "template") return "Restated without a language model.";
  return "";
}

export function ExplainPoints({ page }) {
  const rows = [
    ["What it is", page.what],
    ["Formula", page.formula],
    ["Example", page.example],
    ["Your portfolio", page.yours],
    ["Keep in mind", page.watch],
  ].filter(([, value]) => value);
  return (
    <dl className="explain-points">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className={label === "Formula" ? "explain-formula" : undefined}>{roundFigures(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function ExplainLayer() {
  const [request, setRequest] = useState(null);
  const [chip, setChip] = useState(null);
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [portfoliosReady, setPortfoliosReady] = useState(false);
  const dialogRef = useRef(null);

  useEffect(() => {
    function onExplain(event) {
      const text = String(event.detail?.text || "").trim();
      if (!text) return;
      setChip(null);
      setPortfoliosReady(false);
      setRequest({
        text,
        ticker: event.detail?.ticker || "",
        slug: event.detail?.slug || "",
      });
      window.getSelection()?.removeAllRanges();
    }
    function onSelect(event) {
      if (event.target?.closest?.("[data-explain-root]")) return;
      const selection = window.getSelection();
      const text = selection?.toString().replace(/\s+/g, " ").trim() || "";
      const parent = selection?.anchorNode?.parentElement;
      if (!text || text.length < 2 || text.length > 80 || parent?.closest("input, textarea, select, button")) {
        setChip(null);
        return;
      }
      const rect = selection.getRangeAt(0).getBoundingClientRect();
      if (!rect.width && !rect.height) {
        setChip(null);
        return;
      }
      setChip({
        text,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 120)),
        top: Math.max(8, rect.bottom + 6),
      });
    }
    function onKey(event) {
      if (event.key === "Escape") {
        setRequest(null);
        setChip(null);
      }
    }
    window.addEventListener("finsight:explain", onExplain);
    document.addEventListener("mouseup", onSelect);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("finsight:explain", onExplain);
      document.removeEventListener("mouseup", onSelect);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    if (!request) return undefined;
    let cancelled = false;
    api("/portfolios")
      .then((rows) => {
        if (cancelled) return;
        setPortfolios(rows);
        const stored = sessionStorage.getItem(PORTFOLIO_KEY) || "";
        const chosen = rows.find((row) => row.id === stored) || rows[0];
        setPortfolioId(chosen ? chosen.id : "");
        setPortfoliosReady(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setPortfoliosReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  useEffect(() => {
    if (!request || !portfoliosReady) return undefined;
    let cancelled = false;
    setLoading(true);
    setPage(null);
    setError("");
    api("/learn/explain", {
      method: "POST",
      body: JSON.stringify({
        text: request.text,
        portfolio_id: portfolioId || null,
        ticker: request.ticker || null,
        slug: request.slug || null,
      }),
    })
      .then((body) => {
        if (!cancelled) setPage(body);
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
  }, [request, portfolioId, portfoliosReady]);

  useEffect(() => {
    if (request) dialogRef.current?.focus();
  }, [request, page]);

  if (typeof document === "undefined") return null;

  const chipNode = chip
    ? createPortal(
      <button
        type="button"
        className="explain-chip"
        style={{ left: chip.left, top: chip.top }}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          window.dispatchEvent(new CustomEvent("finsight:explain", { detail: { text: chip.text } }));
        }}
      >
        Explain
      </button>,
      document.body,
    )
    : null;

  const dialog = request
    ? createPortal(
      <div className="explain-backdrop" data-explain-root="" onMouseDown={() => setRequest(null)}>
        <div
          className="explain-card"
          role="dialog"
          aria-modal="true"
          aria-label={page?.title || request.text}
          tabIndex={-1}
          ref={dialogRef}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <header className="explain-head">
            <div>
              <p className="eyebrow">Explanation</p>
              <h2>{page?.title || request.text}</h2>
            </div>
            <button type="button" className="text-button" onClick={() => setRequest(null)}>Close</button>
          </header>
          {portfolios.length ? (
            <label className="field">Portfolio
              <select
                value={portfolioId}
                onChange={(event) => {
                  setPortfolioId(event.target.value);
                  sessionStorage.setItem(PORTFOLIO_KEY, event.target.value);
                }}
              >
                {portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </label>
          ) : null}
          {loading ? <GeneratingStatus phases={EXPLAIN_PHASES} /> : null}
          {error ? <p className="error">{error}</p> : null}
          {page?.source ? <p className="answer-origin">{explainOrigin(page.source)}</p> : null}
          {page ? <ExplainPoints page={page} /> : null}
          {page ? <p className="muted explain-note">{page.disclaimer}</p> : null}
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      {chipNode}
      {dialog}
    </>
  );
}
