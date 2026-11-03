// Every page in the sitemap, and its Greek twin (built, not yet offered), loads with a heading and
// no console error; every link on them to this site answers, and a link to a spot on a page finds
// it there; canonical and language links point at built pages. Links to other sites aren't
// followed (the tests never touch the network beyond the site under test).
import { existsSync, readFileSync } from "node:fs";
import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "./helpers";

const SITE = "https://traceconomics.com";
const SITEMAP = new URL("../../dist/sitemap.xml", import.meta.url);
const offered = existsSync(SITEMAP)
  ? [...readFileSync(SITEMAP, "utf-8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname)
  : [];
const greek = offered.filter((p) => p.startsWith("/en/")).map((p) => p.replace(/^\/en\//, "/el/"));

test("the sitemap lists the pages", () => {
  test.skip(!existsSync(SITEMAP), "needs a build (dist/sitemap.xml)");
  expect(offered.length).toBeGreaterThan(20);
});

for (const path of [...offered, ...greek]) {
  test(`${path} loads, with a heading, and logs no error`, async ({ page }) => {
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

test("every link to this site answers, and every #spot exists on its page", async ({ request }) => {
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
