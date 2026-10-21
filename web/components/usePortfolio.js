"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

const KEY = "finsight_portfolio";

export function usePortfolio() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [email, setEmail] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api("/auth/me")
      .then((user) => {
        if (!cancelled) setEmail(user.email || "");
      })
      .catch(() => {});
    api("/portfolios")
      .then((rows) => {
        if (cancelled) return;
        setPortfolios(rows);
        const stored = sessionStorage.getItem(KEY) || "";
        const chosen = rows.some((row) => row.id === stored) ? stored : (rows[0]?.id || "");
        setPortfolioId(chosen);
        if (chosen) sessionStorage.setItem(KEY, chosen);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onPick(event) {
      const id = event.detail?.id || "";
      if (id) setPortfolioId(id);
    }
    function onRows(event) {
      if (Array.isArray(event.detail?.rows)) setPortfolios(event.detail.rows);
    }
    window.addEventListener("finsight:portfolio", onPick);
    window.addEventListener("finsight:portfolios", onRows);
    return () => {
      window.removeEventListener("finsight:portfolio", onPick);
      window.removeEventListener("finsight:portfolios", onRows);
    };
  }, []);

  function updatePortfolios(value) {
    setPortfolios((current) => {
      const next = typeof value === "function" ? value(current) : value;
      window.dispatchEvent(new CustomEvent("finsight:portfolios", { detail: { rows: next } }));
      return next;
    });
  }

  function selectPortfolio(id) {
    setPortfolioId(id);
    sessionStorage.setItem(KEY, id);
    window.dispatchEvent(new CustomEvent("finsight:portfolio", { detail: { id } }));
  }

  return { portfolios, setPortfolios: updatePortfolios, portfolioId, selectPortfolio, email, ready, error };
}
