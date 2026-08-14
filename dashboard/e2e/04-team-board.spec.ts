import { test, expect, type Page } from "@playwright/test";
import { SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

/** The people table specifically — the chart ships a second, sr-only one. */
const board = (page: Page) => page.getByRole("table", { name: /Engineers ranked by AQ/ });

/**
 * Open the board and wait for the client bundle to take over. The sort headers
 * and the unit toggle are client components; clicking the server-rendered HTML
 * before hydration silently drops the event.
 */
async function openBoard(page: Page) {
  await page.goto(SEEDED);
  await page.waitForLoadState("networkidle");
}

/** Person names only — the cell may also carry a stale-window marker. */
const names = (page: Page) => board(page).locator("tbody tr th a").allTextContents();

/** The values of one column, in the order they are painted. */
async function column(page: Page, index: number) {
  return board(page)
    .locator("tbody tr")
    .evaluateAll((rows, i) => rows.map((r) => r.children[i].textContent!.trim()), index);
}

const AQ = 1;
const TOKENS = 6;

test.describe("Flow 4 · reading the team board", () => {
  test("the board opens ranked by AQ, highest first", async ({ page }) => {
    await page.goto(SEEDED);

    await expect(page.getByRole("heading", { name: "The people" })).toBeVisible();
    // Everyone the seed created is on the board.
    for (const name of ["Ada Lovelace", "Alan Turing", "Grace Hopper", "Katherine J."]) {
      await expect(page.getByRole("rowheader", { name: new RegExp(name) })).toBeVisible();
    }

    const aqs = (await column(page, AQ)).map(Number);
    expect(aqs).toEqual([...aqs].sort((a, b) => b - a));

    // The stat band summarises the same window the table is showing.
    await expect(page.getByText("Team avg AQ")).toBeVisible();
    await expect(page.getByText("Ingest coverage")).toBeVisible();
    await page.screenshot(shot("04-board-default"));
  });

  test("column headers re-sort the board and announce the direction", async ({ page }) => {
    await openBoard(page);
    // Scoped to the table: "Tokens" also names the chart's unit toggle.
    const header = (name: string) => board(page).getByRole("button", { name, exact: false });

    await header("Name").click();
    const sorted = await names(page);
    expect(sorted).toEqual([...sorted].sort((a, b) => a.localeCompare(b)));
    await expect(page.getByRole("columnheader", { name: "Name" })).toHaveAttribute("aria-sort", "ascending");

    // Clicking the active column flips it.
    await header("Name").click();
    expect(await names(page)).toEqual([...sorted].reverse());
    await expect(page.getByRole("columnheader", { name: "Name" })).toHaveAttribute("aria-sort", "descending");

    // Numeric columns start at highest-first.
    await header("Tokens").click();
    const tokens = await column(page, TOKENS);
    const asNum = tokens.map((t) => parseFloat(t));
    expect(asNum).toEqual([...asNum].sort((a, b) => b - a));

    await page.screenshot(shot("04-board-sorted-by-tokens"));
  });

  test("people with no previous window sort last, not first", async ({ page }) => {
    await openBoard(page);
    await board(page).getByRole("button", { name: "Delta", exact: false }).click();

    // Katherine has a single upload, so she has no delta at all. Whichever way
    // the column points, an absent value must not outrank a real one.
    const deltas = await column(page, 4);
    const missing = deltas.filter((d) => !/[+−±]/.test(d));
    expect(missing.length).toBeGreaterThan(0);
    expect(deltas.slice(-missing.length)).toEqual(missing);
  });

  test("the unit toggle switches the chart from tokens to cost", async ({ page }) => {
    await openBoard(page);
    const chart = page.getByRole("group", { name: "Chart unit" });
    await expect(chart.getByRole("button", { name: "Tokens" })).toHaveAttribute("aria-pressed", "true");

    // Bar totals read in billions of tokens...
    await expect(page.getByText(/^\d+\.\d+B$/).first()).toBeVisible();

    await chart.getByRole("button", { name: "Cost" }).click();
    await expect(chart.getByRole("button", { name: "Cost" })).toHaveAttribute("aria-pressed", "true");

    // ...and in dollars once toggled, legend included.
    await expect(page.getByText(/^\$[\d,]+$/).first()).toBeVisible();
    await expect(page.getByText("By model ·")).toBeVisible();

    await page.screenshot(shot("04-board-cost-mode"));
  });

  test("the chart is legible to a screen reader, not just to the eye", async ({ page }) => {
    await page.goto(SEEDED);
    // The stacked bars are decorative; the same numbers exist as a real table.
    const srTable = page.locator("table", { hasText: "Company usage over time, by model" });
    await expect(srTable).toBeAttached();
    await expect(srTable.locator("tbody tr").first().locator("th")).toHaveText(/^\d{4}-\d{2}$/);
  });
});
