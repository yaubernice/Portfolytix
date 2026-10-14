"use client";

import Nav from "../../components/Nav";
import Watchlist from "../../components/Watchlist";

export default function WatchlistPage() {
  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Markets</p>
            <h1>Watchlists</h1>
            <p className="muted">Track the securities that matter to you.</p>
          </div>
        </header>
        <Watchlist />
      </main>
    </>
  );
}
