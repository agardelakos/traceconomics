// Terms that open an explanation (glossary terms, method options). With a mouse, pointing at a term
// shows its explanation and a click goes to its page. From the keyboard and on touch screens, pressing
// it opens the explanation (which holds the link), and Escape or a tap elsewhere closes it.
import { devices, type Page } from "@playwright/test";
import { expect, gwt, m1, test } from "./helpers";

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
  test("pointing at a term opens its explanation; moving away closes it", gwt({
    id: "PW-TERM-001",
    given: ["a reader with a mouse", "the method page, with its first explained term's explanation closed"],
    when: ["the pointer moves onto the term", "the pointer moves away"],
    then: ["the explanation opens", "it closes again"],
  }), async ({ page }) => {
    const { button, pop } = await firstTerm(page);
    await expect(pop).toBeHidden();
    await button.hover();
    await expect(pop).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(pop).toBeHidden();
  });

  test("the explanation stays open while the pointer moves into it", gwt({
    id: "PW-TERM-002",
    given: ["a reader with a mouse", "the method page, with its first explained term's explanation opened by pointing at the term"],
    when: "the pointer moves into the explanation",
    then: "the explanation stays open",
  }), async ({ page }) => {
    const { button, pop } = await firstTerm(page);
    await button.hover();
    await expect(pop).toBeVisible();
    await pop.hover();
    await expect(pop).toBeVisible();
  });

  test("a click on a term goes to its page", gwt({
    id: "PW-TERM-003",
    given: ["a reader with a mouse", "the method page"],
    when: "its first explained term is clicked",
    then: "the browser goes to the page the term's explanation links to",
  }), async ({ page, coverage }) => {
    const { button, href } = await firstTerm(page);
    await coverage.flush();
    await button.click();
    await expect(page).toHaveURL(new RegExp(`${href.replace(/\/$/, "")}/?$`));
  });
});

test("from the keyboard, Enter opens the explanation and Escape closes it", gwt({
  id: "PW-TERM-004",
  given: "the method page, with the keyboard focus on its first explained term",
  when: ["Enter is pressed", "Escape is pressed"],
  then: ["the explanation opens and the page stays where it is", "Escape closes it"],
}), async ({ page }) => {
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

  test("a tap opens the explanation, with its link; a tap elsewhere closes it", gwt({
    id: "PW-TERM-005",
    given: ["a reader on a phone's touch screen", "the method page"],
    when: ["its first explained term is tapped", "the page's main heading is tapped"],
    then: ["the explanation opens, showing its link, and the page stays where it is", "the tap on the heading closes it"],
  }), async ({ page }) => {
    const { button, pop, link } = await firstTerm(page);
    await button.tap();
    await expect(pop).toBeVisible();
    await expect(link).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${PAGE}$`));
    await page.getByRole("heading", { level: 1 }).tap();
    await expect(pop).toBeHidden();
  });
});
