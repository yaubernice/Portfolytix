"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorState, Skeleton, StatusBadge } from "./UI";
import { authenticatedEventStream } from "../lib/api";

const PRESETS = [
  "What drove my portfolio today?",
  "What is my biggest concentration risk?",
  "Summarize my portfolio performance.",
];

export default function PortfolioAssistant({ portfolioId }) {
  const [question, setQuestion] = useState(PRESETS[0]);
  const [text, setText] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const controllerRef = useRef(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  async function ask(event) {
    event.preventDefault();
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setText("");
    setEvidence(null);
    setError("");
    setState("thinking");
    try {
      for await (const message of authenticatedEventStream(
        `/portfolios/${portfolioId}/ask/stream`,
        { question },
        { signal: controller.signal },
      )) {
        if (message.event === "evidence") setEvidence(message.data);
        if (message.event === "text") {
          setState("streaming");
          setText((current) => current + (message.data.delta || ""));
        }
        if (message.event === "done") setState("complete");
        if (message.event === "error") throw new Error(message.data.message || "Assistant provider failed");
      }
    } catch (err) {
      if (err.name === "AbortError") setState("cancelled");
      else {
        setError(err.message);
        setState("error");
      }
    } finally {
      controllerRef.current = null;
    }
  }

  return (
    <section className="panel assistant-panel" aria-live="polite">
      <div className="panel-header">
        <div><h2>Portfolio intelligence</h2><p className="muted">Evidence-based analysis from your portfolio data</p></div>
        <StatusBadge value={state} />
      </div>
      <div className="preset-row" aria-label="Suggested questions">
        {PRESETS.map((preset) => <button type="button" key={preset} onClick={() => setQuestion(preset)}>{preset}</button>)}
      </div>
      <form onSubmit={ask}>
        <label className="field">Question
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={2} maxLength={500} required />
        </label>
        <div className="row">
          <button className="primary" type="submit" disabled={!portfolioId || ["thinking", "streaming"].includes(state)}>Ask FinSight</button>
          {["thinking", "streaming"].includes(state) ? <button type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : null}
        </div>
      </form>
      <ErrorState message={error} />
      {state === "thinking" ? <Skeleton lines={2} label="FinSight is thinking" /> : null}
      {text ? <div className="assistant-output"><p>{text}</p></div> : null}
      {evidence ? (
        <div className="evidence-grid">
          {[...(evidence.facts || []), ...(evidence.metrics || [])].map((item) => (
            <article className="evidence-item" key={`${item.kind}-${item.name}`}>
              <p className="eyebrow">{item.kind}</p><strong>{item.name}</strong><p>{item.value}</p>
              <small className="muted">Source: {item.source}</small>
            </article>
          ))}
        </div>
      ) : null}
      {evidence?.interpretation_source ? <p className="metadata">Interpretation source: {evidence.interpretation_source}</p> : null}
    </section>
  );
}
