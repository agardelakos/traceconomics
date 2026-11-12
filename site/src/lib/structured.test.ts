// The descriptions for search engines: the dataset block and the sitemap.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { dataset, ldJson } from "./structured";
import { sitemap, sitemapXml } from "./sitemap.mjs";

const site = new URL("https://example.org");
const input = {
  site, lang: "en", name: "Greece: Inflation by household", description: "How much prices rose.",
  page: "/en/data/gr/#inflation-by-group",
  metadata: { licence: "CC BY 4.0", first_period: "2008-12", last_period: "2026-09", attribution: "Prices: ELSTAT." },
  place: "Greece", basedOn: ["https://www.statistics.gr/en/home"],
  files: ["/data/v1/gr/m1/latest/downloads/x/m1_rates.csv", "/data/v1/gr/m1/latest/downloads/x/m1_rates.parquet", "/data/v1/gr/m1/latest/metadata.json"],
};

describe("dataset", () => {
  it("gives full addresses, the licence's address and each file's media type", { meta: {
    id: "VT-STRUCT-001",
    given: [
      "a dataset under CC BY 4.0 from 2008-12 to 2026-09",
      "a page and CSV, Parquet and JSON files given as paths on the site",
    ],
    when: "its dataset block is built",
    then: [
      "the dataset's address is the page's full address on the site",
      "the licence is given as Creative Commons BY 4.0's address",
      "the temporal coverage is 2008-12/2026-09",
      "the files' media types are text/csv, application/vnd.apache.parquet and application/json, in order",
      "the first file's address is its full address on the site",
    ],
  } }, () => {
    const d = dataset(input) as any;
    expect(d.url).toBe("https://example.org/en/data/gr/#inflation-by-group");
    expect(d.license).toBe("https://creativecommons.org/licenses/by/4.0/");
    expect(d.temporalCoverage).toBe("2008-12/2026-09");
    expect(d.distribution.map((f: any) => f.encodingFormat)).toEqual(["text/csv", "application/vnd.apache.parquet", "application/json"]);
    expect(d.distribution[0].contentUrl).toBe("https://example.org/data/v1/gr/m1/latest/downloads/x/m1_rates.csv");
  });

  it("refuses a licence or a file type it doesn't know, rather than guess", { meta: {
    id: "VT-STRUCT-002",
    given: "the same dataset with an unknown licence (CC0), or with an .xlsx file",
    when: "its dataset block is built",
    then: [
      "the unknown licence is refused with an error naming the licence",
      "the unknown file type is refused with an error naming the media type",
    ],
  } }, () => {
    expect(() => dataset({ ...input, metadata: { ...input.metadata, licence: "CC0" } })).toThrow(/licence/);
    expect(() => dataset({ ...input, files: ["/data/v1/x.xlsx"] })).toThrow(/media type/);
  });
});

describe("ldJson", () => {
  it("can't close its script element, and reads back the same", { meta: {
    id: "VT-STRUCT-003",
    given: "a value whose text holds a closing script tag, a script and an HTML comment",
    when: "it is written as JSON-LD",
    then: [
      "the written text has no \"<\" character",
      "parsing the text gives back the same value",
    ],
  } }, () => {
    const value = { name: "a </script><script>alert(1)</script> <!-- b" };
    const text = ldJson(value);
    expect(text).not.toContain("<");
    expect(JSON.parse(text)).toEqual(value);
  });
});

describe("sitemapXml", () => {
  it("lists each page in an offered language once, sorted, with full addresses", { meta: {
    id: "VT-STRUCT-004",
    given: [
      "page paths in English and Greek, with and without slashes, one listed twice",
      "English the only offered language",
    ],
    when: "the sitemap is written",
    then: "its addresses are the English pages only, each once, in full with a closing slash, sorted",
  } }, () => {
    const xml = sitemapXml("https://example.org", ["", "en/", "el/", "en/data/gr/", "/en/about", "el/about/", "en/"], ["en"]);
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    expect(locs).toEqual(["https://example.org/en/", "https://example.org/en/about/", "https://example.org/en/data/gr/"]);
  });
});

describe("the sitemap step of the build", () => {
  type Hooks = { "astro:config:done": (o: { config: { site?: string } }) => void; "astro:build:done": (o: { pages: { pathname: string }[]; dir: URL }) => void };
  const pages = [{ pathname: "" }, { pathname: "en/" }, { pathname: "el/data/gr/" }, { pathname: "fr/" }];
  const outDir = () => pathToFileURL(fs.mkdtempSync(path.join(os.tmpdir(), "sitemap-")) + path.sep);

  it("writes sitemap.xml into the build's folder for the languages the site offers", { meta: {
    id: "VT-STRUCT-005",
    given: [
      "the site's address from the Astro config",
      "built pages: the root, the English home, a Greek data page and a page in a language the site has no file for",
      "the site's own list of offered languages",
    ],
    when: "the build finishes",
    then: "the build's folder holds sitemap.xml with the same text the sitemap gives for those pages and the offered languages",
  } }, () => {
    const { hooks } = sitemap() as { hooks: Hooks };
    const dir = outDir();
    hooks["astro:config:done"]({ config: { site: "https://example.org" } });
    hooks["astro:build:done"]({ pages, dir });
    const { offered } = JSON.parse(fs.readFileSync(path.resolve("src/i18n/languages.json"), "utf-8"));
    const written = fs.readFileSync(new URL("sitemap.xml", dir), "utf-8");
    expect(written).toBe(sitemapXml("https://example.org", pages.map((p) => p.pathname), offered));
    expect(written).toContain("<loc>https://example.org/en/</loc>");
    expect(written).not.toContain("/fr/");
  });

  it("stops the build when the Astro config has no site address", { meta: {
    id: "VT-STRUCT-006",
    given: "an Astro config without a site address",
    when: "the build finishes",
    then: [
      "the step throws an error naming the missing setting",
      "no sitemap.xml is written",
    ],
  } }, () => {
    const { hooks } = sitemap() as { hooks: Hooks };
    const dir = outDir();
    hooks["astro:config:done"]({ config: {} });
    expect(() => hooks["astro:build:done"]({ pages, dir })).toThrow(/no `site` in the Astro config/);
    expect(fs.existsSync(new URL("sitemap.xml", dir))).toBe(false);
  });
});
