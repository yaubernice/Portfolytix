"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, Skeleton } from "../../components/UI";
import { api } from "../../lib/api";

export default function LearnIndexPage() {
  const [terms, setTerms] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/learn")
      .then((body) => setTerms(body.terms || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Learning</p>
            <h1>Financial terms</h1>
            <p className="muted">Short explanations of the figures already shown in FinSight. Right-click a term, press Enter or Shift+F10 while it is focused, or press and hold it on a phone.</p>
          </div>
        </header>
        <ErrorState message={error} />
        {loading ? <Skeleton lines={4} label="Loading terms" /> : null}
        {!loading && !terms.length ? <EmptyState title="No terms">The glossary is empty.</EmptyState> : null}
        <div className="stack">
          {terms.map((term) => (
            <Link className="panel learn-index-link" key={term.slug} href={`/learn/${term.slug}`}>
              <strong>{term.title}</strong>
              <span className="muted">{term.summary}</span>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
