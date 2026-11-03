// Terms that open an explanation (glossary terms, method options). With a mouse, pointing at a term
// shows its explanation and a click goes to its page. From the keyboard and on touch screens, pressing
// it opens the explanation (which holds the link), and Escape or a tap elsewhere closes it.
import { devices, type Page } from "@playwright/test";
import { expect, m1, test } from "./helpers";

const PAGE = m1("en", "method/");

/** The page's first term, its explanation and the explanation's link. */
async function firstTerm(page: Page) {
  await page.goto(PAGE);
  const button = page.locator(".term-wrap button.term").first();
  const id = await button.getAttribute("popovertarget");
  const pop = page.locator(`[id="${id}"]`);
  const link = pop.locator("a");          // a role query would skip it while the explanation is closed
  return { button, pop, link, href: (await link.getAttribute("href"))! };
}

test.describe("with a mouse", () => {
  test("pointing at a term opens its explanation; moving away closes it", async ({ page }) => {
    const { button, pop } = await firstTerm(page);
    await expect(pop).toBeHidden();
    await button.hover();
    await expect(pop).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(pop).toBeHidden();
  });

  test("the explanation stays open while the pointer moves into it", async ({ page }) => {
    const { button, pop } = await firstTerm(page);
    await button.hover();
    await expect(pop).toBeVisible();
    await pop.hover();
    await expect(pop).toBeVisible();
  });

  test("a click on a term goes to its page", async ({ page, coverage }) => {
    const { button, href } = await firstTerm(page);
    await coverage.flush();
    await button.click();
    await expect(page).toHaveURL(new RegExp(`${href.replace(/\/$/, "")}/?$`));
  });
});

test("from the keyboard, Enter opens the explanation and Escape closes it", async ({ page }) => {
  const { button, pop } = await firstTerm(page);
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(pop).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`${PAGE}$`));      // no navigation
  await page.keyboard.press("Escape");
  await expect(pop).toBeHidden();
});

test.describe("on a touch screen", () => {
  // A phone's settings, without its browser choice (that can only be set for a whole file).
  const { defaultBrowserType: _, ...phone } = devices["Pixel 7"];
  test.use(phone);

  test("a tap opens the explanation, with its link; a tap elsewhere closes it", async ({ page }) => {
    const { button, pop, link } = await firstTerm(page);
    await button.tap();
    await expect(pop).toBeVisible();
    await expect(link).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${PAGE}$`));
    await page.getByRole("heading", { level: 1 }).tap();
    await expect(pop).toBeHidden();
  });
});
