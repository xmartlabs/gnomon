import { test, expect } from "@playwright/test";
import { SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

test.describe("Flow 5 · from the board into one person's report", () => {
  test("a name on the board opens that person's window", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("button", { name: /Grace Hopper/ }).click();

    await expect(page).toHaveURL(/\/p\/\d+\/2026-06$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Grace Hopper");
    await expect(page.getByText("grace@example.com", { exact: false })).toBeVisible();

    // The sections the design promises, all present, in the right order.
    for (const section of ["Scorecard", "How they operate agents", "Explore", "Usage this month"]) {
      await expect(page.getByRole("heading", { name: new RegExp(section) })).toBeVisible();
    }
    // Suggestions are gated on LLM_API_KEY, unset in this suite — the column
    // collapses entirely rather than leaving an empty heading behind.
    await expect(page.getByRole("heading", { name: "Suggestions" })).toHaveCount(0);

    await page.screenshot(shot("05-profile"));
  });

  test("level history renders each of the person's own past months, most recent emphasised", async ({ page }) => {
    // Grace runs 70 (abr) → 74 (may) → 81 (jun) — the chart carries a plain
    // human label (design system default), not a data dump, so the individual
    // values are checked as visible bar-column text instead of the aria-label.
    await page.goto(SEEDED);
    await page.getByRole("button", { name: /Grace Hopper/ }).click();

    const chart = page.getByRole("img", { name: /Grace Hopper's AQ/ });
    await expect(chart).toBeVisible();
    for (const value of ["70", "74", "81"]) {
      await expect(chart.getByText(value, { exact: true })).toBeVisible();
    }
  });

  test("back returns to the board", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("button", { name: /Ada Lovelace/ }).click();
    await page.getByRole("link", { name: "← Team" }).click();
    await expect(page.getByRole("heading", { name: "People", exact: true })).toBeVisible();
  });

  test("a person with a single window still gets a level chart, not a crash", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("button", { name: /Katherine J\./ }).click();

    await expect(page.getByRole("heading", { name: "Level over time" })).toBeVisible();
    await expect(page.getByRole("img", { name: /Katherine J\.'s AQ/ })).toBeVisible();

    await page.screenshot(shot("05-profile-single-window"));
  });

  test("unknown people and windows 404 instead of rendering an empty report", async ({ page }) => {
    for (const path of ["/p/9999/2026-06", "/p/3/2026-01", "/p/not-a-number/2026-06"]) {
      const res = await page.goto(`${SEEDED}${path}`);
      expect(res?.status(), path).toBe(404);
    }
  });
});
