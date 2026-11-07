// Every page in the sitemap, and its Greek twin (built, not yet offered), loads with a heading and
// no console error; every link on them to this site answers, and a link to a spot on a page finds
// it there; canonical and language links point at built pages. Links to other sites aren't
// followed (the tests never touch the network beyond the site under test).
import { existsSync, readFileSync } from "node:fs";
import type { APIRequestContext } from "@playwright/test";
import { expect, gwt, OFFERED, test } from "./helpers";

const SITE = "https://traceconomics.com";
const SITEMAP = new URL("../../dist/sitemap.xml", import.meta.url);
const offered = existsSync(SITEMAP)
  ? [...readFileSync(SITEMAP, "utf-8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname)
  : [];
const greek = offered.filter((p) => p.startsWith("/en/")).map((p) => p.replace(/^\/en\//, "/el/"));

test("the sitemap lists the pages", gwt({
  id: "PW-LINK-001",
  given: "a built site",
  when: "its sitemap is read",
  then: "it lists more than 20 pages",
}), () => {
  test.skip(!existsSync(SITEMAP), "needs a build (dist/sitemap.xml)");
  expect(offered.length).toBeGreaterThan(20);
});

for (const path of [...offered, ...greek]) {
  test(`${path} loads, with a heading, and logs no error`, gwt({
    id: "PW-LINK-002",
    title: "every page in the sitemap loads, with a heading, and logs no error",
    given: "a page listed in the sitemap, or the Greek twin of an English one",
    when: "it is opened and has finished loading its data",
    then: ["it answers with success (200)", "its first main heading is not empty", "the browser logs no error"],
  }), async ({ page }) => {
    const response = await page.goto(path, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 }).first()).not.toBeEmpty();
  });
}

/** Our own address, as a path on the server under test; null for another site. */
function local(href: string, from: string): URL | null {
  const u = new URL(href, `${SITE}${from}`);
  return u.origin === SITE ? u : null;
}

async function htmlOf(request: APIRequestContext, cache: Map<string, string>, path: string) {
  if (!cache.has(path)) {
    const r = await request.get(path);
    cache.set(path, r.status() === 200 && (r.headers()["content-type"] ?? "").includes("html") ? await r.text() : "");
  }
  return cache.get(path)!;
}

test("every link to this site answers, and every #spot exists on its page", gwt({
  id: "PW-LINK-003",
  given: "every page in the sitemap, and the Greek twin of every English one",
  when: "every link on them to this site (page links, and the page's own canonical, language and other links) is followed",
  then: ["more addresses are found than there are pages in the sitemap, and at least one link to a spot on a page",
    "every linked address answers with success (200)", "every linked spot exists on its page"],
}), async ({ request }) => {
  test.skip(!offered.length, "needs a build (dist/sitemap.xml)");
  test.setTimeout(180_000);
  const pages = new Map<string, string>();
  const targets = new Map<string, string>();          // path -> a page linking to it
  const spots = new Map<string, string>();            // path#id -> a page linking to it
  for (const from of [...offered, ...greek]) {
    const html = await htmlOf(request, pages, from);
    for (const [, href] of html.matchAll(/<(?:a|link)\b[^>]*\bhref="([^"]+)"/g)) {
      if (/^(mailto|tel|javascript):/.test(href)) continue;
      const u = local(href.replaceAll("&amp;", "&"), from);
      if (!u) continue;
      if (!targets.has(u.pathname)) targets.set(u.pathname, from);
      if (u.hash.length > 1) spots.set(`${u.pathname}${u.hash}`, from);
    }
  }
  // A parsing slip would otherwise pass by checking nothing.
  test.info().annotations.push({ type: "checked", description: `${targets.size} addresses, ${spots.size} spots` });
  expect(targets.size).toBeGreaterThan(offered.length);
  expect(spots.size).toBeGreaterThan(0);
  const broken: string[] = [];
  for (const [path, from] of targets) {
    const r = await request.fetch(path, { method: "HEAD" });
    if (r.status() !== 200) broken.push(`${path} (${r.status()}), linked from ${from}`);
  }
  for (const [spot, from] of spots) {
    const [path, id] = spot.split("#");
    const html = await htmlOf(request, pages, path);
    if (html && !html.includes(`id="${decodeURIComponent(id)}"`)) broken.push(`${spot} (no such spot), linked from ${from}`);
  }
  expect(broken).toEqual([]);
});

test("the sitemap lists only pages in offered languages", gwt({
  id: "PW-LINK-004",
  given: "a built site",
  when: "its sitemap's pages are read",
  then: "every page it lists is in a language the site offers",
}), () => {
  test.skip(!offered.length, "needs a build (dist/sitemap.xml)");
  const elsewhere = offered.filter((p) => !OFFERED.some((lang) => p.startsWith(`/${lang}/`)));
  expect(elsewhere).toEqual([]);
});

test("each page has exactly one canonical link, to its own address", gwt({
  id: "PW-LINK-005",
  given: "every page in the sitemap, and the Greek twin of every English one",
  when: "its canonical links are read",
  then: "each page has exactly one, and it points at the page itself",
}), async ({ request }) => {
  test.skip(!offered.length, "needs a build (dist/sitemap.xml)");
  test.setTimeout(120_000);
  const wrong: string[] = [];
  for (const path of [...offered, ...greek]) {
    const html = await (await request.get(path)).text();
    const canonical = [...html.matchAll(/<link\b[^>]*\brel="canonical"[^>]*>/g)].map((m) => m[0].match(/\bhref="([^"]+)"/)?.[1] ?? "");
    if (canonical.length !== 1) wrong.push(`${path}: ${canonical.length} canonical links`);
    else if (new URL(canonical[0], SITE).pathname !== path) wrong.push(`${path}: canonical is ${canonical[0]}`);
  }
  expect(wrong).toEqual([]);
});
