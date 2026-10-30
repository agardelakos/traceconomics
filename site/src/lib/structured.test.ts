// The descriptions for search engines: the dataset block and the sitemap.
import { describe, expect, it } from "vitest";
import { dataset, ldJson } from "./structured";
import { sitemapXml } from "./sitemap.mjs";

const site = new URL("https://example.org");
const input = {
  site, lang: "en", name: "Greece: Inflation by household", description: "How much prices rose.",
  page: "/en/data/gr/#inflation-by-group",
  metadata: { licence: "CC BY 4.0", first_period: "2008-12", last_period: "2026-09", attribution: "Prices: ELSTAT." },
  place: "Greece", basedOn: ["https://www.statistics.gr/en/home"],
  files: ["/data/v1/gr/m1/latest/downloads/x/m1_rates.csv", "/data/v1/gr/m1/latest/downloads/x/m1_rates.parquet", "/data/v1/gr/m1/latest/metadata.json"],
};

describe("dataset", () => {
  it("gives full addresses, the licence's address and each file's media type", () => {
    const d = dataset(input) as any;
    expect(d.url).toBe("https://example.org/en/data/gr/#inflation-by-group");
    expect(d.license).toBe("https://creativecommons.org/licenses/by/4.0/");
    expect(d.temporalCoverage).toBe("2008-12/2026-09");
    expect(d.distribution.map((f: any) => f.encodingFormat)).toEqual(["text/csv", "application/vnd.apache.parquet", "application/json"]);
    expect(d.distribution[0].contentUrl).toBe("https://example.org/data/v1/gr/m1/latest/downloads/x/m1_rates.csv");
  });

  it("refuses a licence or a file type it doesn't know, rather than guess", () => {
    expect(() => dataset({ ...input, metadata: { ...input.metadata, licence: "CC0" } })).toThrow(/licence/);
    expect(() => dataset({ ...input, files: ["/data/v1/x.xlsx"] })).toThrow(/media type/);
  });
});

describe("ldJson", () => {
  it("can't close its script element, and reads back the same", () => {
    const value = { name: "a </script><script>alert(1)</script> <!-- b" };
    const text = ldJson(value);
    expect(text).not.toContain("<");
    expect(JSON.parse(text)).toEqual(value);
  });
});

describe("sitemapXml", () => {
  it("lists each page in an offered language once, in order, with full addresses", () => {
    const xml = sitemapXml("https://example.org", ["", "en/", "el/", "en/data/gr/", "/en/about", "el/about/", "en/"], ["en"]);
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    expect(locs).toEqual(["https://example.org/en/", "https://example.org/en/about/", "https://example.org/en/data/gr/"]);
  });
});
