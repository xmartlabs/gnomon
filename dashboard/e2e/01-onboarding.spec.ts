import { test, expect } from "@playwright/test";
import { EMPTY, SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

test.describe("Flow 1 · a fresh deployment", () => {
  test("an empty dashboard tells you exactly how to fill it", async ({ page }) => {
    await page.goto(EMPTY);

    // The masthead is honest about having nobody yet.
    await expect(page.getByRole("heading", { level: 1 })).toContainText("gnomon");
    await expect(page.getByText("0 engineers")).toBeVisible();

    // The onboarding block carries the exact command to run — not a generic
    // "no data" shrug.
    await expect(page.getByText("No uploads yet")).toBeVisible();
    await expect(page.locator("code")).toHaveText(
      "xl-ai-insights --mirdash-base=http://localhost:3000"
    );

    // No table, no chart, nothing pretending to have data.
    await expect(page.locator("table")).toHaveCount(0);

    await page.screenshot(shot("01-empty-state"));
  });

  test("a seeded dashboard shows the team instead", async ({ page }) => {
    await page.goto(SEEDED);
    await expect(page.getByText("4 engineers")).toBeVisible();
    await expect(page.getByText("No uploads yet")).toHaveCount(0);
  });
});
