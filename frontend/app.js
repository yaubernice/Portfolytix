
const API_BASE_URL = "https://portfolytix-9839b.containers.snapdeploy.app";
const tokenKey = "finsight_token";
const authPanel = document.querySelector("#auth");
const appPanel = document.querySelector("#app");
const who = document.querySelector("#who");
const authError = document.querySelector("#auth-error");
const statusLine = document.querySelector("#status");
const portfolioSelect = document.querySelector("#portfolio");

document.querySelector("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  authenticate("/auth/login", new FormData(event.currentTarget), false);
});

document.querySelector("#register").addEventListener("click", () => {
  authenticate("/auth/register", new FormData(document.querySelector("#login-form")), true);
});

document.querySelector("#logout").addEventListener("click", () => {
  sessionStorage.removeItem(tokenKey);
  showAuth();
});

document.querySelectorAll("nav button[data-panel]").forEach((button) => {
  button.addEventListener("click", () => selectPanel(button.dataset.panel));
});

document.querySelector("#portfolio-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await run(async () => {
    await api("/portfolios", { method: "POST", body: JSON.stringify(readForm(form)) });
    form.reset();
    await loadPortfolios();
  });
});

document.querySelector("#trade-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = selectedPortfolio();
  if (!id) return;
  await run(async () => {
    await api(`/portfolios/${id}/transactions`, {
      method: "POST",
      body: JSON.stringify(readForm(event.currentTarget)),
    });
    await showTransactions();
  });
});

document.querySelector("#screen-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await run(async () => {
    const body = await api("/screen", {
      method: "POST",
      body: JSON.stringify(readForm(event.currentTarget)),
    });
    renderTable("#screen-table", body.items, ["ticker", "sector", "roe", "pe_ratio", "revenue_growth"]);
  });
});

document.querySelector("#natural-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await run(async () => {
    const body = await api("/screen/natural", {
      method: "POST",
      body: JSON.stringify(readForm(event.currentTarget)),
    });
    document.querySelector("#natural-view").innerHTML =
      `<p class="note">Parser: ${escapeHtml(body.parser)}. Applied: ${escapeHtml(JSON.stringify(body.applied))}</p>`;
    renderTable("#natural-view", body.items, ["ticker", "sector", "roe", "pe_ratio", "revenue_growth"], true);
  });
});

document.querySelector("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = selectedPortfolio();
  if (!id) return;
  await run(async () => {
    const body = await api(`/portfolios/${id}/ask`, {
      method: "POST",
      body: JSON.stringify(readForm(event.currentTarget)),
    });
    const facts = body.facts.map((item) => `<li>${escapeHtml(item.name)}: ${escapeHtml(item.value)}</li>`).join("");
    const metrics = body.metrics.map((item) => `<li>${escapeHtml(item.name)}: ${escapeHtml(item.value)}</li>`).join("");
    document.querySelector("#ask-view").innerHTML = `
      <article class="note"><p>${escapeHtml(body.interpretation)}</p><p>${escapeHtml(body.disclaimer)}</p></article>
      <div class="cards">
        <article><h2>Facts</h2><ul>${facts}</ul></article>
        <article><h2>Metrics</h2><ul>${metrics}</ul></article>
      </div>`;
  });
});

portfolioSelect.addEventListener("change", () => refreshVisible());

if (sessionStorage.getItem(tokenKey)) {
  enterApp();
} else {
  showAuth();
}

async function authenticate(path, formData, created) {
  authError.textContent = "";
  try {
    const body = Object.fromEntries(formData.entries());
    const result = await api(path, { method: "POST", body: JSON.stringify(body) });
    if (created) {
      authError.textContent = "Account created. Log in with the same password.";
      return;
    }
    sessionStorage.setItem(tokenKey, result.access_token);
    await enterApp();
  } catch (error) {
    authError.textContent = error.message;
  }
}

async function enterApp() {
  authPanel.hidden = true;
  appPanel.hidden = false;
  const me = await api("/auth/me");
  who.textContent = me.email;
  await loadPortfolios();
  await selectPanel("portfolio");
}

function showAuth() {
  authPanel.hidden = false;
  appPanel.hidden = true;
  who.textContent = "Not signed in";
}

async function selectPanel(name) {
  document.querySelectorAll("nav button[data-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === name);
  });
  document.querySelectorAll("[data-view]").forEach((view) => {
    view.hidden = view.dataset.view !== name;
  });
  await refreshVisible();
}

async function refreshVisible() {
  const visible = document.querySelector("[data-view]:not([hidden])");
  if (!visible) return;
  const name = visible.dataset.view;
  if (name === "portfolio") await loadPortfolios();
  if (name === "holdings") await showHoldings();
  if (name === "analytics") await showAnalytics();
  if (name === "transactions") await showTransactions();
  if (name === "jobs") await showJobs();
  if (name === "cache") await showCache();
}

async function loadPortfolios() {
  const rows = await api("/portfolios");
  const current = portfolioSelect.value;
  portfolioSelect.innerHTML = rows.map((row) =>
    `<option value="${row.id}">${escapeHtml(row.name)}</option>`
  ).join("");
  if (rows.some((row) => row.id === current)) portfolioSelect.value = current;
  renderTable("#portfolio-table", rows, ["name", "description", "id"]);
}

async function showHoldings() {
  const id = selectedPortfolio();
  if (!id) return;
  await run(async () => {
    renderTable("#holdings-table", await api(`/portfolios/${id}/holdings`), ["ticker", "quantity"]);
  });
}

async function showAnalytics() {
  const id = selectedPortfolio();
  if (!id) return;
  await run(async () => {
    const body = await api(`/portfolios/${id}/analytics`);
    const cards = ["total_return", "volatility", "sharpe_ratio", "max_drawdown"].map((key) =>
      `<article><h2>${key}</h2><p>${escapeHtml(String(body[key]))}</p></article>`
    ).join("");
    document.querySelector("#analytics-view").innerHTML = `<div class="cards">${cards}</div>`;
    renderTable("#analytics-view", body.allocation, ["ticker", "quantity", "price", "weight"], true);
  });
}

async function showTransactions() {
  const id = selectedPortfolio();
  if (!id) return;
  await run(async () => {
    renderTable(
      `#transactions-table`,
      await api(`/portfolios/${id}/transactions`),
      ["timestamp", "ticker", "transaction_type", "quantity", "price"],
    );
  });
}

async function showJobs() {
  await run(async () => {
    const body = await api("/jobs");
    renderTable("#jobs-table", body.items, ["job_name", "status", "started_at", "error"]);
  });
}

async function showCache() {
  await run(async () => {
    const body = await api("/cache/stats");
    document.querySelector("#cache-view").innerHTML = `<div class="cards">${
      Object.entries(body).map(([key, value]) =>
        `<article><h2>${escapeHtml(key)}</h2><p>${escapeHtml(String(value))}</p></article>`
      ).join("")
    }</div>`;
  });
}

function selectedPortfolio() {
  if (!portfolioSelect.value) {
    statusLine.textContent = "Create a portfolio first.";
    return "";
  }
  return portfolioSelect.value;
}

function readForm(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function run(action) {
  statusLine.textContent = "";
  try {
    await action();
  } catch (error) {
    statusLine.textContent = error.message;
  }
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const token = sessionStorage.getItem(tokenKey);
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function renderTable(selector, rows, columns, append = false) {
  const host = document.querySelector(selector);
  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>${columns.map((column) => `<th>${column}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of rows || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = columns.map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`).join("");
    body.append(tr);
  }
  table.append(body);
  if (!append) host.replaceChildren(table);
  else host.append(table);
}

function formatCell(value) {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
