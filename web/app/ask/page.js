"use client";

import { useEffect, useRef, useState } from "react";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "../../components/UI";
import { api, authenticatedEventStream } from "../../lib/api";

export default function AskPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [text, setText] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [error, setError] = useState("");
  const [state, setState] = useState("idle");
  const controllerRef = useRef(null);

  useEffect(() => {
    api("/portfolios").then((rows) => {
      setPortfolios(rows);
      if (rows[0]) setPortfolioId(rows[0].id);
    }).catch((err) => setError(err.message));
  }, []);

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError("");
    setText("");
    setEvidence(null);
    setState("thinking");
    try {
      for await (const message of authenticatedEventStream(
        `/portfolios/${portfolioId}/ask/stream`,
        { question: form.get("question") },
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
      if (err.name === "AbortError") {
        setState("cancelled");
      } else {
        setError(err.message);
        setState("error");
      }
    } finally {
      controllerRef.current = null;
    }
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Assistant</p><h1>Ask about your portfolio</h1><p className="muted">Answers stream progressively and cite portfolio evidence.</p></div><StatusBadge value={state} /></header>
        <div className="split-grid">
          <section className="panel">
            <form onSubmit={submit}>
              <label className="field">Portfolio<select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>{portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
              <label className="field">Question<textarea name="question" rows={4} maxLength={500} required placeholder="What drove my portfolio today?" /></label>
              <div className="row">
                <button className="primary" type="submit" disabled={!portfolioId || ["thinking", "streaming"].includes(state)}>Ask FinSight</button>
                {["thinking", "streaming"].includes(state) ? <button type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : null}
              </div>
            </form>
            <ErrorState message={error} />
          </section>
          <aside className="panel">
            <h2>How answers work</h2>
            <p className="muted">The model receives your question and calculated portfolio evidence. It cannot query the database. The badge says llm when a model wrote the answer. With no model configured, a local template restates that evidence.</p>
          </aside>
        </div>
        <section className="panel" aria-live="polite" aria-busy={["thinking", "streaming"].includes(state)}>
          <div className="panel-header"><h2>Answer</h2>{evidence?.interpretation_source ? <span className="status">Source: {evidence.interpretation_source}</span> : null}</div>
          {state === "thinking" ? <Skeleton lines={3} label="FinSight is thinking" /> : null}
          {state === "idle" ? <EmptyState title="Ask a portfolio question">The answer and its supporting evidence will appear here.</EmptyState> : null}
          {state === "cancelled" && !text ? <EmptyState title="Response cancelled">Your question was not completed.</EmptyState> : null}
          {text ? <div className="assistant-output"><p>{text}</p></div> : null}
          {evidence?.disclaimer ? <p className="muted">{evidence.disclaimer}</p> : null}
        </section>
        {evidence ? (
          <section className="panel">
            <div className="panel-header"><h2>Evidence</h2><span className="muted">Database and calculated sources</span></div>
            <div className="evidence-grid">
              {[...(evidence.facts || []), ...(evidence.metrics || [])].map((item) => (
                <article className="evidence-item" key={`${item.kind}-${item.name}`}>
                  <p className="eyebrow">{item.kind}</p><strong>{item.name}</strong><p>{item.value}</p><small className="muted">Source: {item.source}</small>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </>
  );
}
