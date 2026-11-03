// The header's theme setting: device setting, light or dark. A choice of light or dark is kept in
// this browser (one localStorage value) so it holds from page to page and applies before the page
// is drawn; "device setting" forgets it. The control says so next to the options.
import { expect, t, test } from "./helpers";
import type { Page } from "@playwright/test";

const SETTINGS = t("en", "settings.label");

/** Picks a theme in the header's settings menu, opening it only if it's closed (a click closes it). */
async function choose(page: Page, theme: "system" | "light" | "dark") {
  const radio = page.getByRole("radio", { name: t("en", `theme.${theme}`) });
  if (!(await radio.isVisible())) await page.getByRole("button", { name: SETTINGS }).click();
  await radio.check();
}

const stored = (page: Page) => page.evaluate(() => localStorage.getItem("theme"));
const html = (page: Page) => page.locator("html");

for (const theme of ["dark", "light"] as const) {
  test(`choosing ${theme} applies it and keeps it in this browser`, async ({ page }) => {
    await page.goto("/en/");
    await choose(page, theme);
    await expect(html(page)).toHaveAttribute("data-theme", theme);
    expect(await stored(page)).toBe(theme);
  });
}

test("the menu says the choice stays in this browser", async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.locator("#settings-menu").getByText(t("en", "theme.stored"))).toBeVisible();
});

test("the choice holds on the next page, ticked in the menu", async ({ page }) => {
  await page.goto("/en/");
  await choose(page, "dark");
  await page.goto("/en/about/");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.getByRole("radio", { name: t("en", "theme.dark") })).toBeChecked();
});

test("device setting forgets the choice", async ({ page }) => {
  await page.goto("/en/");
  await choose(page, "dark");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await choose(page, "system");
  await expect(html(page)).not.toHaveAttribute("data-theme");
  expect(await stored(page)).toBeNull();
});

test("a stored choice applies before the page's scripts run", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  // Only the head's small script (public/theme.js) sets the attribute from storage; the header's
  // script just ticks the matching option. So if it's there at DOMContentLoaded, it came first.
  await page.goto("/en/", { waitUntil: "domcontentloaded" });
  expect(await html(page).getAttribute("data-theme")).toBe("dark");
});

test("an unknown stored value means the device setting", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("theme", "purple"));
  await page.goto("/en/");
  await expect(html(page)).not.toHaveAttribute("data-theme");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.getByRole("radio", { name: t("en", "theme.system") })).toBeChecked();
});

test("with storage blocked, the choice still applies to this page, without errors", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new DOMException("blocked", "SecurityError"); } });
  });
  await page.goto("/en/");
  await choose(page, "dark");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("the menu's copy of the setting works and matches the other", async ({ page }) => {
    await page.goto("/en/");
    await page.getByRole("button", { name: t("en", "nav.menu") }).click();
    const menu = page.getByRole("navigation", { name: t("en", "nav.label") });
    await menu.getByRole("radio", { name: t("en", "theme.light") }).check();
    await expect(html(page)).toHaveAttribute("data-theme", "light");
    expect(await stored(page)).toBe("light");
    // The settings button's copy (hidden at this width) follows.
    await expect(page.locator('input[name="theme"][value="light"]')).toBeChecked();
  });
});
