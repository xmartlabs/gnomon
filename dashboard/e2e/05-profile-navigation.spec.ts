import { test, expect } from "@playwright/test";
import { SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

const monthNav = (page: import("@playwright/test").Page) => ({
  prev: page.getByRole("link", { name: /^Previous window/ }),
  next: page.getByRole("link", { name: /^Next window/ }),
});

test.describe("Flow 5 · from the board into one person's report", () => {
  test("a name on the board opens that person's window", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("link", { name: "Grace Hopper" }).click();

    await expect(page).toHaveURL(/\/p\/\d+\/2026-06$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Grace Hopper");
    await expect(page.getByText("grace@example.com")).toBeVisible();

    // The sections the design promises, all present.
    for (const section of ["Level over time", "How you operate agents", "Scorecard", "Explore", "Usage"]) {
      await expect(page.getByRole("heading", { name: section })).toBeVisible();
    }
    await page.screenshot(shot("05-profile"));
  });

  test("month arrows walk the person's own history and stop at its ends", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("link", { name: "Grace Hopper" }).click();
    const nav = monthNav(page);

    // Newest window: there is nothing after it, so no next link exists at all.
    await expect(nav.next).toHaveCount(0);
    await expect(nav.prev).toBeVisible();

    await nav.prev.click();
    await expect(page).toHaveURL(/2026-05$/);
    await expect(page.getByText("74", { exact: true }).first()).toBeVisible();

    await nav.prev.click();
    await expect(page).toHaveURL(/2026-04$/);
    // Oldest window: no previous link, but you can still walk forward.
    await expect(nav.prev).toHaveCount(0);
    await expect(nav.next).toBeVisible();

    await nav.next.click();
    await expect(page).toHaveURL(/2026-05$/);
  });

  test("the delta compares against the window immediately before it", async ({ page }) => {
    // Grace runs 70 → 74 → 81, so June must read +7 against May, not +11.
    await page.goto(SEEDED);
    await page.getByRole("link", { name: "Grace Hopper" }).click();
    await expect(page.getByText(/\+7 pts vs 2026-05/)).toBeVisible();
  });

  test("back returns to the board", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("link", { name: "Ada Lovelace" }).click();
    await page.getByRole("link", { name: "← The people" }).click();
    await expect(page.getByRole("heading", { name: "The people" })).toBeVisible();
  });

  test("a person with a single window still gets their history section", async ({ page }) => {
    await page.goto(SEEDED);
    await page.getByRole("link", { name: "Katherine J." }).click();

    await expect(page.getByRole("heading", { name: "Level over time" })).toBeVisible();
    await expect(page.getByText("1 window")).toBeVisible();
    const nav = monthNav(page);
    await expect(nav.prev).toHaveCount(0);
    await expect(nav.next).toHaveCount(0);

    await page.screenshot(shot("05-profile-single-window"));
  });

  test("unknown people and windows 404 instead of rendering an empty report", async ({ page }) => {
    for (const path of ["/p/9999/2026-06", "/p/3/2026-01", "/p/not-a-number/2026-06"]) {
      const res = await page.goto(`${SEEDED}${path}`);
      expect(res?.status(), path).toBe(404);
    }
  });
});
