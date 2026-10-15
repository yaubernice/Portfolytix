"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { EmptyState, ErrorState, money, Pagination, percent, Skeleton, StatusBadge, Toast } from "./UI";
import { useQuotes } from "./useQuotes";

const PAGE_SIZE = 12;

export default function Watchlist() {
  const { quotes, status } = useQuotes();
  const [lists, setLists] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [toast, setToast] = useState("");

  const loadLists = useCallback(async () => {
    const body = await api("/watchlists?limit=100");
    setLists(body.items);
    setActiveId((current) => current || body.items[0]?.id || "");
  }, []);

  const loadDetail = useCallback(async () => {
    if (!activeId) {
      setDetail(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setDetail(await api(`/watchlists/${activeId}?limit=${PAGE_SIZE}&offset=${offset}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [activeId, offset]);

  useEffect(() => {
    loadLists().catch((err) => {
      setError(err.message);
      setLoading(false);
    });
  }, [loadLists]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  useEffect(() => {
    if (!search.trim()) {
      setResults([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      api(`/securities/search?q=${encodeURIComponent(search)}&limit=8`)
        .then((body) => setResults(body.items))
        .catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [search]);

  async function createList(event) {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      const created = await api("/watchlists", { method: "POST", body: JSON.stringify({ name: newName.trim() }) });
      setNewName("");
      await loadLists();
      setActiveId(created.id);
      setOffset(0);
      setToast("Watchlist created");
    } catch (err) { setError(err.message); }
  }

  async function renameList() {
    const name = window.prompt("Watchlist name", detail?.name || "");
    if (!name?.trim()) return;
    try {
      await api(`/watchlists/${activeId}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
      await Promise.all([loadLists(), loadDetail()]);
      setToast("Watchlist renamed");
    } catch (err) { setError(err.message); }
  }

  async function deleteList() {
    if (!window.confirm(`Delete "${detail?.name}"?`)) return;
    try {
      await api(`/watchlists/${activeId}`, { method: "DELETE" });
      setDetail(null);
      setOffset(0);
      const body = await api("/watchlists?limit=100");
      setLists(body.items);
      setActiveId(body.items[0]?.id || "");
      setToast("Watchlist deleted");
    } catch (err) { setError(err.message); }
  }

  async function addItem(security) {
    try {
      await api(`/watchlists/${activeId}/items`, { method: "POST", body: JSON.stringify({ security_id: security.id }) });
      setSearch("");
      await Promise.all([loadLists(), loadDetail()]);
      setToast(`${security.ticker} added`);
    } catch (err) { setError(err.message); }
  }

  async function removeItem(item) {
    try {
      await api(`/watchlists/${activeId}/items/${item.security_id}`, { method: "DELETE" });
      await Promise.all([loadLists(), loadDetail()]);
      setToast(`${item.ticker} removed`);
    } catch (err) { setError(err.message); }
  }

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-header">
          <div>
            <h2>Your watchlists</h2>
            <p className="muted">Organize securities and follow live worker quotes.</p>
          </div>
          <StatusBadge value={status} />
        </div>
        <div className="watchlist-tabs" role="tablist" aria-label="Watchlists">
          {lists.map((list) => (
            <button key={list.id} type="button" role="tab" aria-selected={activeId === list.id} onClick={() => { setActiveId(list.id); setOffset(0); }}>
              {list.name} <span className="muted">({list.item_count})</span>
            </button>
          ))}
        </div>
        <form className="row" onSubmit={createList}>
          <label className="sr-only" htmlFor="watchlist-name">New watchlist name</label>
          <input id="watchlist-name" value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="New watchlist name" maxLength={200} />
          <button className="primary" type="submit">Create</button>
        </form>
      </div>

      <ErrorState message={error} retry={() => { loadLists(); loadDetail(); }} />
      {loading ? <div className="panel"><Skeleton lines={5} label="Loading watchlist" /></div> : null}
      {!loading && lists.length === 0 ? <EmptyState title="No watchlists yet">Create one above to start tracking securities.</EmptyState> : null}
      {!loading && detail ? (
        <section className="panel" aria-labelledby="active-watchlist-title">
          <div className="panel-header">
            <div>
              <h2 id="active-watchlist-title">{detail.name}</h2>
              <p className="muted">{detail.items_total} {detail.items_total === 1 ? "security" : "securities"}</p>
            </div>
            <div className="row">
              <button type="button" onClick={renameList}>Rename</button>
              <button type="button" className="danger-button" onClick={deleteList}>Delete</button>
            </div>
          </div>
          <div className="search-picker">
            <label className="field">
              Add a security
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search ticker or company" />
            </label>
            {search ? (
              <div className="search-picker-results" aria-live="polite">
                {results.map((security) => (
                  <button type="button" key={security.id} onClick={() => addItem(security)}>
                    <strong>{security.ticker}</strong><span>{security.name}</span><small>{security.exchange}</small>
                  </button>
                ))}
                {results.length === 0 ? <p className="search-empty">No matches</p> : null}
              </div>
            ) : null}
          </div>
          {detail.items.length === 0 ? <EmptyState title="This watchlist is empty">Search above to add its first security.</EmptyState> : (
            <>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Security</th><th>Exchange</th><th className="numeric">Last</th><th className="numeric">Change</th><th>Freshness</th><th><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>
                    {detail.items.map((item) => {
                      const quote = quotes[item.ticker];
                      const change = Number(quote?.change);
                      const tone = change > 0 ? "up" : change < 0 ? "down" : "";
                      return (
                        <tr key={item.id}>
                          <td><Link className="ticker-link" href={`/securities/${item.ticker}`}>{item.ticker}</Link><br /><span className="muted">{item.name}</span></td>
                          <td>{item.exchange}</td>
                          <td className={`numeric ${tone}`}>{money(quote?.price)}</td>
                          <td className={`numeric ${tone}`}>{quote ? `${money(quote.change)} (${percent(quote.change_percent)})` : "—"}</td>
                          <td><StatusBadge value={quote?.timeliness || "waiting"} /></td>
                          <td className="numeric"><button type="button" onClick={() => removeItem(item)} aria-label={`Remove ${item.ticker}`}>Remove</button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination offset={detail.items_offset} limit={detail.items_limit} total={detail.items_total} onChange={setOffset} />
            </>
          )}
        </section>
      ) : null}
      <Toast message={toast} onDismiss={() => setToast("")} />
    </div>
  );
}
