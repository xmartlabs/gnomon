import { test, expect, request as pwRequest } from "@playwright/test";
import http from "node:http";
import { SEEDED } from "../playwright.config";
import { makeSummary } from "../tests/fixtures/summary";


/**
 * Walks the CLI's actual sequence: sign in through the browser form, catch the
 * tokens on a loopback server, then POST a summary with one of them exactly as
 * gnomon/upload/mirdash.py:_upload_summary does.
 */
async function signInForTokens(page: import("@playwright/test").Page, email: string, name: string) {
  const received: URL[] = [];
  // Port 0: the OS picks a free one, exactly as the CLI's own listener does.
  const server = http.createServer((req, res) => {
    received.push(new URL(req.url!, "http://127.0.0.1"));
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end("<h1>ok</h1>");
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const callback = `http://127.0.0.1:${(server.address() as import("node:net").AddressInfo).port}/callback`;
  try {
    await page.goto(`${SEEDED}/cli-auth?redirect_uri=${encodeURIComponent(callback)}&count=2`);
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Team token").fill("e2e-team-token");
    await page.getByRole("button", { name: "Authorize" }).click();
    await expect(page.getByRole("heading", { name: "ok" })).toBeVisible();
    return JSON.parse(received[0].searchParams.get("tokens")!) as string[];
  } finally {
    await new Promise((r) => server.close(r));
  }
}

test.describe("Flow 3 · the CLI uploads a month", () => {
  test("a signed-in token can ingest, and the report URL it returns resolves", async ({ page }) => {
    const [token] = await signInForTokens(page, "newcomer@example.com", "Ada Byron");
    const api = await pwRequest.newContext();

    // The real payload shape: tz-aware ISO bounds, as parse_window produces.
    const summary = makeSummary({
      context: {
        date_range: ["2026-02-01T00:00:00-03:00", "2026-07-31T00:00:00-03:00"],
        total_sessions: 88,
      },
      profile: { aq: { aq_0_100: 77, tier: "Proficient" } },
    });

    const res = await api.post(`${SEEDED}/api/gnomon/ingest`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: summary,
    });
    expect(res.status()).toBe(200);

    // The CLI prints this URL; it must actually resolve on this server.
    const { reportUrl } = await res.json();
    expect(reportUrl).toMatch(/^\/p\/\d+\/2026-07$/);

    await page.goto(`${SEEDED}${reportUrl}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ada Byron");
    await expect(page.getByText("77", { exact: true }).first()).toBeVisible();
    await page.screenshot({ path: "test-results/flows/03-uploaded-profile.png", fullPage: true });

    // The new person is now on the team board. Every row is a "button" (the
    // whole row is the click target — see DataTable), so match on that role
    // rather than a table-header cell, which this design doesn't use.
    await page.goto(SEEDED);
    await expect(page.getByRole("button", { name: /Ada Byron/ })).toBeVisible();
    await api.dispose();
  });

  test("the contract's failure modes answer the way the CLI expects", async ({ page }) => {
    const [token] = await signInForTokens(page, "newcomer@example.com", "Ada Byron");
    const api = await pwRequest.newContext();
    const post = (data: unknown, auth?: string) =>
      api.post(`${SEEDED}/api/gnomon/ingest`, {
        headers: { ...(auth ? { Authorization: auth } : {}), "Content-Type": "application/json" },
        data: data as object,
      });

    // The CLI surfaces the response body verbatim, so the message must be useful.
    const noToken = await post(makeSummary());
    expect(noToken.status()).toBe(401);

    const garbage = await post({ nope: true }, `Bearer ${token}`);
    expect(garbage.status()).toBe(400);
    expect((await garbage.json()).error).toContain("context");

    const oversized = await post(
      makeSummary({ context: { client_version: "x".repeat(1_000_000) } }),
      `Bearer ${token}`
    );
    expect(oversized.status()).toBe(413);

    await api.dispose();
  });

  test("re-uploading a thinner month does not overwrite the better one", async ({ page }) => {
    const [token, token2] = await signInForTokens(page, "shrinker@example.com", "Alan M. Turing");
    const api = await pwRequest.newContext();
    const upload = (sessions: number, auth: string, extra: object = {}) =>
      api.post(`${SEEDED}/api/gnomon/ingest`, {
        headers: { Authorization: `Bearer ${auth}`, "Content-Type": "application/json" },
        data: makeSummary({
          context: {
            date_range: ["2026-03-01T00:00:00-03:00", "2026-08-31T00:00:00-03:00"],
            total_sessions: sessions,
          },
          ...extra,
        }),
      });

    const first = await upload(400, token);
    const { reportUrl } = await first.json();

    // Claude Code's shrinking retention makes a later run legitimately smaller.
    expect((await upload(40, token2)).status()).toBe(200);
    await page.goto(`${SEEDED}${reportUrl}`);
    await expect(page.getByText("400", { exact: true })).toBeVisible(); // kept the fuller snapshot

    // ...unless the CLI explicitly forces it.
    await upload(40, token2, { force: true });
    await page.reload();
    await expect(page.getByText("40", { exact: true })).toBeVisible();

    await api.dispose();
  });
});
