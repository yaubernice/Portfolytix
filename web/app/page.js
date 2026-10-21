"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, readToken, writeToken } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState("signin");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "register") {
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setMode("signin");
        setShowPassword(false);
        setNotice("Account created. Sign in with the same password.");
        return;
      }
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      writeToken(body.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (readToken()) router.replace("/dashboard");
  }, [router]);

  const signingIn = mode === "signin";

  return (
    <main className="auth-page">
      <section className="auth-welcome" aria-labelledby="auth-title">
        <p className="auth-brand"><span aria-hidden="true">Px</span> Portfolytix</p>
        <h1 id="auth-title">Know what you own. Understand why it moves.</h1>
        <p className="auth-lead">Figures come from the transactions and prices stored for a portfolio. Portfolytix does not tell you to buy or sell, and it does not forecast a future result.</p>
        <ul className="auth-points">
          <li>See what a portfolio is worth, and which holdings moved it.</li>
          <li>Ask a question. The answer uses those figures, or says the evidence does not contain it.</li>
          <li>Quotes can be delayed. A refresh does not make a delayed quote live.</li>
        </ul>
        <div className="auth-motif" aria-hidden="true">
          <p>Weights in a portfolio</p>
          <div className="auth-bar"><span style={{ width: "62%" }} />Largest holding</div>
          <div className="auth-bar"><span style={{ width: "24%" }} />Next holding</div>
          <div className="auth-bar"><span style={{ width: "14%" }} />The rest</div>
        </div>
        <p className="auth-caption">A drawing of weights. Not a live portfolio, and not a return.</p>
      </section>
      <section className="auth-form-wrap">
        <form className="auth-form" onSubmit={submit} aria-busy={busy}>
          <div className="auth-switch" role="group" aria-label="Account action">
            <button type="button" aria-pressed={signingIn} onClick={() => { setMode("signin"); setError(""); }}>Sign in</button>
            <button type="button" aria-pressed={!signingIn} onClick={() => { setMode("register"); setError(""); setNotice(""); }}>Create account</button>
          </div>
          <h2>{signingIn ? "Sign in" : "Create account"}</h2>
          <p className="muted">{signingIn ? "Use the email and password for this workspace." : "Create an account with an email and a password of at least 8 characters."}</p>
          <label className="field" htmlFor="auth-email">Email
            <input id="auth-email" name="email" type="email" required autoComplete="username" inputMode="email" disabled={busy} />
          </label>
          <div className="field">
            <label htmlFor="auth-password">Password</label>
            <span className="auth-password">
              <input
                id="auth-password"
                name="password"
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                autoComplete={signingIn ? "current-password" : "new-password"}
                disabled={busy}
              />
              <button type="button" aria-pressed={showPassword} aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((current) => !current)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </span>
          </div>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? (signingIn ? "Signing in…" : "Creating account…") : (signingIn ? "Log in" : "Create account")}
          </button>
          {notice ? <p className="auth-notice" role="status">{notice}</p> : null}
          <p className="error" role={error ? "alert" : undefined}>{error}</p>
        </form>
      </section>
    </main>
  );
}
