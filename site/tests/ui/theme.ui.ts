// The header's theme setting: device setting, light or dark. A choice of light or dark is kept in
// this browser (one localStorage value) so it holds from page to page and applies before the page
// is drawn; "device setting" forgets it. The control says so next to the options.
import { expect, gwt, t, test } from "./helpers";
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
  test(`choosing ${theme} applies it and keeps it in this browser`, gwt({
    id: "PW-THEME-001",
    title: "choosing a theme applies it and keeps it in this browser",
    given: "the home page",
    when: "a theme, light or dark, is chosen in the header's settings",
    then: ["the page takes that theme", "the choice is kept in this browser's storage"],
  }), async ({ page }) => {
    await page.goto("/en/");
    await choose(page, theme);
    await expect(html(page)).toHaveAttribute("data-theme", theme);
    expect(await stored(page)).toBe(theme);
  });
}

test("the menu says the choice stays in this browser", gwt({
  id: "PW-THEME-002",
  given: "the home page",
  when: "the header's settings menu is opened",
  then: "it says the choice is kept in this browser",
}), async ({ page }) => {
  await page.goto("/en/");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.locator("#settings-menu").getByText(t("en", "theme.stored"))).toBeVisible();
});

test("the choice holds on the next page, ticked in the menu", gwt({
  id: "PW-THEME-003",
  given: "the dark theme, chosen on the home page",
  when: ["another page (About) opens", "the settings menu is opened there"],
  then: ["that page is dark too", "dark is the option ticked in the menu"],
}), async ({ page }) => {
  await page.goto("/en/");
  await choose(page, "dark");
  await page.goto("/en/about/");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.getByRole("radio", { name: t("en", "theme.dark") })).toBeChecked();
});

test("device setting forgets the choice", gwt({
  id: "PW-THEME-004",
  given: "the dark theme, chosen on the home page",
  when: "the device setting is chosen",
  then: ["the page no longer sets a theme of its own", "nothing is kept in this browser's storage for the theme"],
}), async ({ page }) => {
  await page.goto("/en/");
  await choose(page, "dark");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
  await choose(page, "system");
  await expect(html(page)).not.toHaveAttribute("data-theme");
  expect(await stored(page)).toBeNull();
});

test("a stored choice applies before the page's scripts run", gwt({
  id: "PW-THEME-005",
  given: "a dark theme kept in this browser's storage",
  when: "a page opens, and its content is read but its scripts haven't run yet",
  then: "the page is already dark",
}), async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  // Only the head's small script (public/theme.js) sets the attribute from storage; the header's
  // script just ticks the matching option. So if it's there at DOMContentLoaded, it came first.
  await page.goto("/en/", { waitUntil: "domcontentloaded" });
  expect(await html(page).getAttribute("data-theme")).toBe("dark");
});

test("an unknown stored value means the device setting", gwt({
  id: "PW-THEME-006",
  given: "a theme kept in this browser's storage that the site doesn't know",
  when: ["a page opens", "the settings menu is opened"],
  then: ["the page sets no theme of its own", "the device setting is the option ticked"],
}), async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("theme", "purple"));
  await page.goto("/en/");
  await expect(html(page)).not.toHaveAttribute("data-theme");
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.getByRole("radio", { name: t("en", "theme.system") })).toBeChecked();
});

test("with storage blocked, the choice still applies to this page, without errors", gwt({
  id: "PW-THEME-007",
  given: "a browser that refuses the site any storage",
  when: "the dark theme is chosen on the home page",
  then: ["the page turns dark", "the browser logs no error"],
}), async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new DOMException("blocked", "SecurityError"); } });
  });
  await page.goto("/en/");
  await choose(page, "dark");
  await expect(html(page)).toHaveAttribute("data-theme", "dark");
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("the menu's copy of the setting works and matches the other", gwt({
    id: "PW-THEME-008",
    given: "the home page on a phone",
    when: ["the menu is opened", "light is chosen in the menu's copy of the theme setting"],
    then: ["the page takes the light theme", "the choice is kept in this browser's storage",
      "the settings button's copy of the setting (hidden at this width) has light ticked too"],
  }), async ({ page }) => {
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

test("on a first visit the control starts on the device setting, with nothing stored", gwt({
  id: "PW-THEME-009",
  given: "a first visit, with nothing stored",
  when: ["the home page opens", "the settings menu is opened"],
  then: ["the page sets no theme of its own and nothing is stored", "the device setting is the option ticked"],
}), async ({ page }) => {
  await page.goto("/en/");
  await expect(html(page)).not.toHaveAttribute("data-theme");
  expect(await stored(page)).toBeNull();
  await page.getByRole("button", { name: SETTINGS }).click();
  await expect(page.getByRole("radio", { name: t("en", "theme.system") })).toBeChecked();
});

const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test("the device setting follows the system", gwt({
  id: "PW-THEME-010",
  given: "the home page on the device setting, with the device set to light",
  when: "the device switches to dark",
  then: "the background changes with the device",
}), async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/en/");
  const light = await background(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => background(page)).not.toBe(light);
});

test("a choice overrides the device setting", gwt({
  id: "PW-THEME-011",
  given: "the home page, its light background noted, then the device switched to dark",
  when: ["light is chosen", "then dark is chosen"],
  then: ["light brings back the light background, though the device is dark", "dark brings back the device's dark background"],
}), async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/en/");
  const light = await background(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => background(page)).not.toBe(light);
  const dark = await background(page);
  await choose(page, "light");
  await expect.poll(() => background(page)).toBe(light);
  await choose(page, "dark");
  await expect.poll(() => background(page)).toBe(dark);
});
