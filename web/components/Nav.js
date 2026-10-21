"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, readToken } from "../lib/api";
import { usePortfolio } from "./usePortfolio";
import { CompanyLogo } from "./UI";

const GROUPS = [
  ["Your money", [
    ["/dashboard", "Dashboard"],
    ["/portfolio", "Portfolio"],
    ["/watchlist", "Watchlist"],
  ]],
  ["Discover", [
    ["/ideas", "Ideas"],
    ["/news", "News"],
    ["/screen", "Screening"],
    ["/ask", "Ask"],
  ]],
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { portfolios, portfolioId, selectPortfolio, email } = usePortfolio();
  const [ready, setReady] = useState(false);
  const [theme, setTheme] = useState("light");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!readToken()) {
      router.replace("/");
      return;
    }
    const savedTheme = localStorage.getItem("finsight_theme");
    const nextTheme = savedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = nextTheme;
    setTheme(nextTheme);
    setReady(true);
  }, [router]);

  useEffect(() => {
    const expired = () => router.replace("/");
    window.addEventListener("finsight:auth-expired", expired);
    return () => window.removeEventListener("finsight:auth-expired", expired);
  }, [router]);

  useEffect(() => {
    if (query.trim().length < 1) {
      setResults([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const body = await api(`/securities/search?q=${encodeURIComponent(query.trim())}&limit=6`, {
          signal: controller.signal,
        });
        setResults(body.items || []);
      } catch (error) {
        if (error.name !== "AbortError") setResults([]);
      } finally {
        setSearching(false);
      }
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("finsight_theme", next);
    document.documentElement.dataset.theme = next;
  }

  if (!ready) return null;

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`} aria-label="Primary navigation">
        <Link className="brand" href="/dashboard" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark" aria-hidden="true">Px</span>
          <span>
            <strong>Portfolytix</strong>
            <small>Understand your investments</small>
          </span>
        </Link>
        <nav>
          {GROUPS.map(([label, links]) => (
            <div className="nav-group" key={label}>
              <p className="nav-label">{label}</p>
              {links.map(([href, name]) => {
                const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));
                return (
                  <Link key={href} href={href} aria-current={active ? "page" : undefined} onClick={() => setMenuOpen(false)}>
                    {name}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <Link href="/data" onClick={() => setMenuOpen(false)}>Data status</Link>
          <span className="user-label" title={email || "Signed in"}>{email || "Signed in"}</span>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              clearToken();
              router.replace("/");
            }}
          >
            Log out
          </button>
        </div>
      </aside>
      {menuOpen ? <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} /> : null}
      <header className="topbar">
        <button className="menu-button" type="button" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
          Menu
        </button>
        {portfolios.length ? (
          <label className="field portfolio-switch">
            Portfolio
            <select aria-label="Portfolio" value={portfolioId} onChange={(event) => selectPortfolio(event.target.value)}>
              {portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        ) : null}
        <div className="global-search">
          <label className="sr-only" htmlFor="security-search">Search securities</label>
          <input
            id="security-search"
            type="search"
            placeholder="Search ticker or company"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setQuery("");
                event.currentTarget.blur();
              }
            }}
            role="combobox"
            aria-autocomplete="list"
            aria-controls="security-search-results"
            aria-expanded={Boolean(query)}
            autoComplete="off"
          />
          {query ? (
            <>
              <p className="sr-only" aria-live="polite">{searching ? "Searching" : `${results.length} results`}</p>
              <div id="security-search-results" className="search-results" role="listbox" aria-label="Security results">
                {results.map((item) => (
                  <Link key={item.id} href={`/securities/${item.ticker}`} role="option" onClick={() => setQuery("")}>
                    <CompanyLogo ticker={item.ticker} size={24} />
                    <strong>{item.ticker}</strong>
                    <span>{item.name}</span>
                    <small>{item.exchange}</small>
                  </Link>
                ))}
              </div>
              {!searching && results.length === 0 ? <p className="search-empty">No matching securities</p> : null}
            </>
          ) : null}
        </div>
        <button type="button" className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>
    </>
  );
}
