"use client";

import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import { EmptyState, ErrorState, Skeleton, StatusBadge, dateTime } from "../../components/UI";
import { api } from "../../lib/api";

export default function DataStatusPage() {
  const [system, setSystem] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api("/status"), api("/jobs?limit=8")])
      .then(([statusBody, jobsBody]) => {
        setSystem(statusBody);
        setJobs(jobsBody.items || []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">System</p>
            <h1>Data status</h1>
            <p className="muted">Where quotes and daily history come from. This is operational detail, not a view of your portfolio.</p>
          </div>
        </header>
        <ErrorState message={error} />
        {loading ? <Skeleton lines={4} label="Loading data status" /> : null}
        {system ? (
          <section className="workspace-block">
            <h2>Providers</h2>
            <dl className="detail-list">
              <div><dt>Platform</dt><dd><StatusBadge value={system.status || "unknown"} /></dd></div>
              <div><dt>Quote provider</dt><dd>{system.provider?.name || "—"}</dd></div>
              <div><dt>Historical provider</dt><dd>{system.provider?.historical_provider || "—"}</dd></div>
              <div><dt>Quotes in the store</dt><dd>{system.provider?.quote_count ?? "—"}</dd></div>
              <div><dt>Last ingestion</dt><dd>{dateTime(system.ingestion?.finished_at)}</dd></div>
              <div><dt>Ingestion state</dt><dd><StatusBadge value={system.ingestion?.status || "unavailable"} /></dd></div>
              <div><dt>Failed symbols</dt><dd>{system.ingestion?.failed_ticker_count ?? "—"}</dd></div>
              <div><dt>Quote worker</dt><dd><StatusBadge value={system.worker ? "connected" : "unavailable"} /></dd></div>
            </dl>
          </section>
        ) : null}
        <section className="workspace-block">
          <h2>Recent ingestion runs</h2>
          {jobs.length === 0 && !loading ? <EmptyState title="No job history">Ingestion runs will appear here after the nightly history job.</EmptyState> : null}
          {jobs.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Job</th><th>Status</th><th>Provider</th><th>Started</th><th className="numeric">Bars written</th></tr></thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.job_name}</td>
                      <td><StatusBadge value={job.status} /></td>
                      <td>{job.provider || "—"}</td>
                      <td>{dateTime(job.started_at)}</td>
                      <td className="numeric">{job.upserted < 0 ? "Not counted" : job.upserted}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </main>
    </>
  );
}
