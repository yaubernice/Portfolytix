"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, readToken, writeToken } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      writeToken(body.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  }

  async function register(event) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget.form);
    try {
      await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      setError("Account created. Log in with the same password.");
    } catch (err) {
      setError(err.message);
    }
  }

  if (typeof window !== "undefined" && readToken()) {
    router.replace("/dashboard");
  }

  return (
    <main className="login-shell">
      <header className="page-header">
        <div><p className="eyebrow">FinSight</p><h1>Financial intelligence workspace</h1><p className="muted">Sign in to access portfolios, markets, and research.</p></div>
      </header>
      <section className="panel">
        <form onSubmit={submit}>
          <h2>Sign in</h2>
          <label className="field">Email <input name="email" type="email" required autoComplete="username" /></label>
          <label className="field">Password <input name="password" type="password" required minLength={8} autoComplete="current-password" /></label>
          <div className="row">
            <button className="primary" type="submit">Log in</button>
            <button type="button" onClick={register}>Create account</button>
          </div>
          <p className="error">{error}</p>
        </form>
      </section>
    </main>
  );
}
