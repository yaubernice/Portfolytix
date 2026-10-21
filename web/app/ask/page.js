"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerText, EvidenceList, answerOrigin } from "../../components/EvidenceList";
import GeneratingStatus, { ASK_PHASES } from "../../components/GeneratingStatus";
import Nav from "../../components/Nav";
import { ErrorState, StatusBadge } from "../../components/UI";
import { api, authenticatedEventStream } from "../../lib/api";

export default function AskPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
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
    setAsked(String(form.get("question") || ""));
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
        if (message.event === "done") {
          setState("complete");
          if (message.data.interpretation_source) {
            setEvidence((current) => (
              current ? { ...current, interpretation_source: message.data.interpretation_source } : current
            ));
          }
        }
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
              <label className="field">Question<textarea name="question" rows={4} maxLength={500} required placeholder="What is the overall ROE of my portfolio?" /></label>
              <div className="row">
                <button className="primary" type="submit" disabled={!portfolioId || ["thinking", "streaming"].includes(state)}>Ask Portfolytix</button>
                {["thinking", "streaming"].includes(state) ? <button type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : null}
              </div>
            </form>
            <p className="muted compact-note">Figures are calculated for this portfolio before any wording is written. Ask for a chart and the picture is drawn from those figures. A future line is not drawn. The label under the answer says whether a configured model wrote the words.</p>
            <ErrorState message={error} />
          </section>
          <section className="panel" aria-live="polite" aria-busy={["thinking", "streaming"].includes(state)}>
            <div className="panel-header"><h2>Answer</h2>{evidence?.interpretation_source ? <p className="answer-origin">{answerOrigin(evidence.interpretation_source)}</p> : null}</div>
            {state === "thinking" ? <GeneratingStatus phases={ASK_PHASES} /> : null}
            {state === "idle" ? <p className="muted">The answer will appear here.</p> : null}
            {state === "cancelled" && !text ? <p className="muted">Response cancelled. Ask again when you want to continue.</p> : null}
            {text ? <AnswerText text={text} evidence={evidence} question={asked} streaming={state === "streaming"} /> : null}
            {evidence?.disclaimer ? <p className="muted">{evidence.disclaimer}</p> : null}
          </section>
        </div>
        {evidence ? (
          <details className="panel evidence-panel" open>
            <summary>Evidence behind this answer</summary>
            <EvidenceList facts={evidence.facts} metrics={evidence.metrics} />
          </details>
        ) : null}
      </main>
    </>
  );
}
