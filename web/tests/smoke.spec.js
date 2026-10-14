import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const security = {
  id: "00000000-0000-4000-8000-000000000201",
  ticker: "AAPL",
  name: "Apple Inc.",
  exchange: "NASDAQ",
  sector: "Technology",
  country: "US",
  currency: "USD",
  asset_type: "equity",
  provider: "seed",
  provider_symbol: "AAPL",
  is_active: true,
};

async function mockAuthenticatedApp(page) {
  await page.addInitScript((securityRow) => {
    window.fetch = async (input, options = {}) => {
      const url = new URL(String(input), window.location.origin);
      let body = [];
      if (url.pathname.endsWith("/watchlists") && (options.method || "GET") === "GET") {
        body = {
          items: [{ id: "wl-1", name: "Core", item_count: 1 }],
          total: 1,
          limit: 100,
          offset: 0,
        };
      } else if (url.pathname.endsWith("/watchlists/wl-1")) {
        body = {
          id: "wl-1",
          name: "Core",
          item_count: 1,
          items_total: 1,
          items_limit: 12,
          items_offset: 0,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          items: [{
            id: "item-1",
            security_id: securityRow.id,
            ticker: "AAPL",
            name: "Apple Inc.",
            exchange: "NASDAQ",
            created_at: "2026-01-01T00:00:00Z",
          }],
        };
      } else if (url.pathname.endsWith("/securities/search")) {
        body = { items: [securityRow], total: 1, limit: 8, offset: 0 };
      } else if (url.pathname.endsWith("/auth/me")) {
        body = { email: "test@example.com" };
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    const NativeWebSocket = window.WebSocket;
    class MockWebSocket {
      constructor(url, protocols) {
        if (!String(url).includes("/ws/quotes")) {
          return new NativeWebSocket(url, protocols);
        }
        setTimeout(() => {
          this.onopen?.();
          this.onmessage?.({
            data: JSON.stringify({
              type: "snapshot",
              quotes: [{
                ticker: "AAPL",
                price: "190",
                change: "5",
                change_percent: "0.027",
                timeliness: "realtime",
                source: "test",
              }],
            }),
          });
        }, 0);
      }
      close() {}
    }
    window.WebSocket = MockWebSocket;
  }, security);
  await page.goto("/");
  await page.evaluate(() => sessionStorage.setItem("finsight_token", "test-token"));
}

test("login is accessible and submits through the API", async ({ page }) => {
  await page.addInitScript(() => {
    window.fetch = async () => new Response(
      JSON.stringify({ access_token: "test-token" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.getByLabel("Email").fill("test@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("watchlist search and live quote smoke", async ({ page }) => {
  await mockAuthenticatedApp(page);
  await page.goto("/watchlist");
  await expect(
    page.getByRole("heading", { name: "Watchlists", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("connected", { exact: true })).toBeVisible();
  await page.getByLabel("Search securities").fill("Apple");
  await expect(page.getByRole("option", { name: /AAPL/ })).toBeVisible();
  const results = await new AxeBuilder({ page })
    .exclude(".quote-status")
    .analyze();
  expect(results.violations).toEqual([]);
});
