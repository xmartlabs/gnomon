import { test, expect, type Page } from "@playwright/test";
import http from "node:http";
import { SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

// Bound at runtime, not hard-coded: a busy port would fail the suite before it
// tested any behaviour, and the CLI itself picks a free one too.
let callbackPort = 0;
const callbackUrl = () => `http://127.0.0.1:${callbackPort}/callback`;
/** What the CLI actually opens: gnomon/upload/auth.py starts a loopback server. */
const signInUrl = (count = 3) =>
  `${SEEDED}/cli-auth?redirect_uri=${encodeURIComponent(callbackUrl())}&count=${count}`;

/**
 * The real thing rather than a route stub: gnomon/upload/auth.py binds a
 * one-shot HTTP server on 127.0.0.1:<port> and reads the tokens off the
 * callback query. Running an actual server proves the redirect the dashboard
 * emits is one a listening CLI can consume.
 */
const received: URL[] = [];
let loopback: http.Server;

test.beforeAll(async () => {
  loopback = http.createServer((req, res) => {
    received.push(new URL(req.url!, callbackUrl()));
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end("<h1>CLI got the tokens</h1>");
  });
  await new Promise<void>((resolve) => loopback.listen(0, "127.0.0.1", resolve));
  callbackPort = (loopback.address() as import("node:net").AddressInfo).port;
});

test.afterAll(async () => {
  await new Promise((resolve) => loopback.close(resolve));
});

async function fillAndSubmit(page: Page, token: string) {
  await page.getByLabel("Name").fill("Grace Hopper");
  await page.getByLabel("Email").fill("grace@example.com");
  await page.getByLabel("Team token").fill(token);
  await page.getByRole("button", { name: "Authorize" }).click();
}

test.describe("Flow 2 · an engineer signs the CLI in", () => {
  test("the sign-in page states what leaves the machine", async ({ page }) => {
    await page.goto(signInUrl());

    await expect(page.getByRole("heading", { name: "Authorize upload" })).toBeVisible();
    // The privacy claim is the reason anyone agrees to this at all.
    await expect(page.getByText(/Only summary statistics are uploaded/)).toBeVisible();
    // The page shows which loopback port it will hand the tokens back to.
    await expect(page.getByText(`127.0.0.1:${callbackPort}`)).toBeVisible();

    await page.screenshot(shot("02-cli-signin"));
  });

  test("a wrong team token bounces back with an error and keeps the CLI's params", async ({ page }) => {
    await page.goto(signInUrl());
    await fillAndSubmit(page, "not-the-team-token");

    await expect(page).toHaveURL(/\/cli-auth\?/);
    await expect(page.getByText("Invalid team token")).toBeVisible();
    // The callback and count survive the bounce, so the retry still works.
    const url = new URL(page.url());
    expect(url.searchParams.get("redirect_uri")).toBe(callbackUrl());
    expect(url.searchParams.get("count")).toBe("3");

    await page.screenshot(shot("02-cli-signin-rejected"));
  });

  test("the correct token redirects to the CLI's loopback with N tokens", async ({ page }) => {
    received.length = 0;
    await page.goto(signInUrl(3));
    await fillAndSubmit(page, "e2e-team-token");

    // The browser landed on the CLI's own loopback server, not on the dashboard.
    await expect(page.getByRole("heading", { name: "CLI got the tokens" })).toBeVisible();
    expect(received).toHaveLength(1);

    const seen = received;
    const tokens = JSON.parse(seen[0].searchParams.get("tokens")!);
    expect(tokens).toHaveLength(3);
    // Distinct credentials — one per month the CLI plans to upload.
    expect(new Set(tokens).size).toBe(3);

    // Grace is already seeded, so the CLI learns which months it can skip.
    const history = JSON.parse(seen[0].searchParams.get("uploaded_history")!);
    expect(history.outcome).toBe("valid");
    expect(history.months.map((m: { monthKey: string }) => m.monthKey)).toEqual([
      "2026-04", "2026-05", "2026-06",
    ]);
    // The planner metadata the CLI needs to avoid re-uploading every run.
    expect(history.months[0]).toHaveProperty("scoreContractId");
  });

  test("a non-loopback redirect_uri is refused before the form is shown", async ({ page }) => {
    await page.goto(`${SEEDED}/cli-auth?redirect_uri=${encodeURIComponent("https://evil.example/cb")}&count=1`);

    await expect(page.getByRole("heading", { name: "Nothing to authorize" })).toBeVisible();
    await expect(page.getByLabel("Team token")).toHaveCount(0);

    await page.screenshot(shot("02-cli-signin-refused"));
  });
});
