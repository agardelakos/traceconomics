// The sitemap (/sitemap.xml), written after the build from the pages Astro built: every page in an
// offered language (src/i18n/languages.json), so a language not offered yet stays out of search
// engines' lists as it stays out of the site's links. The root address only sends readers on to a
// language, so it isn't listed. No <lastmod>: a build date would make two builds of the same data
// differ, and the pages carry their data's dates themselves.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** The sitemap's text for these page paths ("en/data/gr/" and so on) on this site. */
export function sitemapXml(site, pathnames, offered) {
  const urls = [...new Set(pathnames.map((p) => p.replace(/^\/+/, "")))]
    .filter((p) => offered.includes(p.split("/")[0]))
    .map((p) => new URL(p.endsWith("/") ? p : `${p}/`, site).href)
    .sort();
  return [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`,
    ...urls.map((u) => `  <url><loc>${u}</loc></url>`),
    `</urlset>`,
    "",
  ].join("\n");
}

export function sitemap() {
  let site;
  return {
    name: "traceconomics-sitemap",
    hooks: {
      "astro:config:done": ({ config }) => { site = config.site; },
      "astro:build:done": ({ pages, dir }) => {
        if (!site) throw new Error("sitemap: no `site` in the Astro config");
        const languages = new URL("../i18n/languages.json", import.meta.url);
        const { offered } = JSON.parse(readFileSync(languages, "utf-8"));
        const out = fileURLToPath(new URL("sitemap.xml", dir));
        writeFileSync(out, sitemapXml(site, pages.map((p) => p.pathname), offered));
      },
    },
  };
}
