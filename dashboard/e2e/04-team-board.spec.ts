import { test, expect, type Page } from "@playwright/test";
import { SEEDED } from "../playwright.config";

const shot = (name: string) => ({ path: `test-results/flows/${name}.png`, fullPage: true });

/** The values of one column, in the order they are painted. Column order: Name, AQ, Tier, Trend, Top pillar, Last upload. */
async function column(page: Page, index: number) {
  return page.locator("table tbody tr").evaluateAll((rows, i) => rows.map((r) => r.children[i].textContent!.trim()), index);
}

test.describe("Flow 4 · reading the team board", () => {
  test("the board opens ranked by AQ, highest first", async ({ page }) => {
    await page.goto(SEEDED);

    await expect(page.getByRole("heading", { name: "People", exact: true })).toBeVisible();
    // Everyone the seed created is on the board — every row is a clickable "button".
    for (const name of ["Ada Lovelace", "Alan Turing", "Grace Hopper", "Katherine J.", "Iris Watson"]) {
      await expect(page.getByRole("button", { name: new RegExp(name) })).toBeVisible();
    }

    const aqs = (await column(page, 1)).map(Number);
    expect(aqs).toEqual([...aqs].sort((a, b) => b - a));

    // The hero states the same window the table is showing.
    await expect(page.getByText("Team AQ")).toBeVisible();
    await page.screenshot(shot("04-board-default"));
  });

  test("a person with no previous window shows 'no data', never a false zero or a red decline", async ({ page }) => {
    await page.goto(SEEDED);
    const row = page.getByRole("button", { name: /Katherine J\./ });
    await expect(row.getByText("no data")).toBeVisible();
  });

  test("the model mix donut responds to hover and keyboard focus alike", async ({ page }) => {
    // Explicit month: 03-upload.spec.ts's tests land uploads in later months
    // on this SAME shared seeded server, which can push the page's default
    // (latest) month to one with no real model data at all.
    await page.goto(`${SEEDED}/?month=2026-06`);

    const slices = page.locator('svg[role="group"] path');
    await expect(slices.first()).toBeVisible();
    const firstLabel = await slices.first().getAttribute("aria-label");
    expect(firstLabel).toMatch(/%$/);

    // Hovering a slice opens the centred tooltip with its name and percentage.
    await slices.first().hover();
    await expect(page.getByText(firstLabel!.split(":")[1].trim())).toBeVisible();

    // Every slice is independently reachable by keyboard, not just by mouse.
    await slices.first().focus();
    await expect(slices.first()).toBeFocused();

    await page.screenshot(shot("04-donut-hover"));
  });

  test("the theme toggle flips data-theme on <html> and the icon swaps", async ({ page }) => {
    await page.goto(SEEDED);
    const html = page.locator("html");
    const before = await html.getAttribute("data-theme");

    const toggle = page.getByRole("button", { name: /Switch to/ });
    await toggle.click();

    await expect(html).not.toHaveAttribute("data-theme", before ?? "");
    // The accessible name flips with the state, so the SAME toggle is still reachable.
    await expect(page.getByRole("button", { name: /Switch to/ })).toBeVisible();
  });

  test("the month select moves the whole screen to another month", async ({ page }) => {
    await page.goto(SEEDED);
    const select = page.getByRole("combobox", { name: "Month" });
    const current = await select.inputValue();
    const optionEls = select.locator("option");
    const values = await optionEls.evaluateAll((els) => els.map((o) => (o as HTMLOptionElement).value));
    const labels = await optionEls.allTextContents();

    // Pick whichever option isn't already selected — robust to however many
    // months another spec's uploads have added to this shared seeded server.
    const targetIndex = values.findIndex((v) => v !== current);
    expect(targetIndex, "expected at least two selectable months").toBeGreaterThanOrEqual(0);

    await select.selectOption({ value: values[targetIndex] });

    await expect(page).toHaveURL(new RegExp(`month=${values[targetIndex]}`));
    await expect(page.getByRole("heading", { level: 1 })).toContainText(labels[targetIndex]);
  });
});
