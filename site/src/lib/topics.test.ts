import { afterEach, describe, expect, it } from "vitest";
import { analyticsOn, BEACON } from "./analytics";
import { flag } from "./flags";
import { GLOSSARY_CATEGORIES } from "./glossary";
import { countries, countryHref, countryPaths, dataCountries, dataHref, m1Text, officialSources, topic, topicHref, topicPath, TOPICS } from "./topics";

describe("topics", () => {
  it("each have a unique slug, and live ones cover at least one country", () => {
    expect(new Set(TOPICS.map((x) => x.slug)).size).toBe(TOPICS.length);
    for (const x of TOPICS.filter((x) => x.status === "live")) expect(x.countries.length).toBeGreaterThan(0);
  });

  it("are found by slug, or refused", () => {
    expect(topic("inflation-by-group").status).toBe("live");
    expect(() => topic("no-such-topic")).toThrow(/no topic/);
  });

  it("give addresses only for pages that exist", () => {
    expect(topicHref("en", "inflation-by-group")).toBe("/en/inflation-by-group/");
    expect(topicHref("el", "inflation-by-group", "gr")).toBe("/el/gr/inflation-by-group/");
    expect(topicHref("en", "inflation-by-group", "gr", "explore")).toBe("/en/gr/inflation-by-group/explore/");
    expect(topicHref("en", "inflation-by-group", "gr", "method/weights-timing")).toBe("/en/gr/inflation-by-group/method/weights-timing/");
    const planned = TOPICS.find((x) => x.status === "planned")!;
    expect(() => topicHref("en", planned.slug)).toThrow(/planned/);
    expect(() => topicHref("en", "inflation-by-group", "zz")).toThrow(/no page for "zz"/);
    expect(() => topicHref("en", "inflation-by-group", "gr", "nope")).toThrow(/no section/);
  });

  it("give the path inside a language", () => {
    expect(topicPath("inflation-by-group")).toBe("inflation-by-group");
    expect(topicPath("inflation-by-group", "gr")).toBe("gr/inflation-by-group");
    expect(topicPath("inflation-by-group", "gr", "explore")).toBe("gr/inflation-by-group/explore");
  });

  it("build one page per language and country", () => {
    const paths = countryPaths("inflation-by-group", ["el", "en"]);
    expect(paths).toHaveLength(2 * topic("inflation-by-group").countries.length);
    expect(paths).toContainEqual({ params: { lang: "en", country: "gr" } });
  });
});

describe("countries", () => {
  it("are the live topics' countries, as two-letter codes", () => {
    expect(countries()).toContain("gr");
    for (const c of countries()) expect(c).toMatch(/^[a-z]{2}$/);
    expect(dataCountries()).toEqual(countries());
  });

  it("have a page and a data page, and an unknown one has neither", () => {
    expect(countryHref("en", "gr")).toBe("/en/gr/");
    expect(dataHref("en")).toBe("/en/data/");
    expect(dataHref("el", "gr")).toBe("/el/data/gr/");
    expect(() => countryHref("en", "zz")).toThrow();
    expect(() => dataHref("en", "zz")).toThrow();
  });

  it("each have a statistics office, then Eurostat", () => {
    const sources = officialSources();
    expect(sources.at(-1)!.key).toBe("eurostat");
    expect(sources).toHaveLength(dataCountries().length + 1);
  });

  it("each have a flag, drawn as a hidden SVG; a country without one stops the build", () => {
    for (const c of countries()) {
      const svg = flag(c);
      expect(svg).toMatch(/^<svg [^>]*aria-hidden="true"/);
      expect(svg).toMatch(/<\/svg>$/);
    }
    expect(() => flag("zz")).toThrow(/no flag/);
  });

  it("have their own written texts, never Greece's borrowed", () => {
    expect(m1Text("gr", "en", "method")).toBe("en/method");
    expect(() => m1Text("zz", "en", "method")).toThrow(/write its own/);
  });
});

describe("the glossary's categories", () => {
  it("are fixed and distinct", () => {
    expect(new Set(GLOSSARY_CATEGORIES).size).toBe(GLOSSARY_CATEGORIES.length);
  });
});

describe("the visit counter", () => {
  const before = process.env.TRACECONOMICS_ANALYTICS;
  afterEach(() => {
    if (before === undefined) delete process.env.TRACECONOMICS_ANALYTICS;
    else process.env.TRACECONOMICS_ANALYTICS = before;
  });

  it("is on only in release builds", () => {
    delete process.env.TRACECONOMICS_ANALYTICS;
    expect(analyticsOn()).toBe(false);
    process.env.TRACECONOMICS_ANALYTICS = "yes";
    expect(analyticsOn()).toBe(false);
    process.env.TRACECONOMICS_ANALYTICS = "on";
    expect(analyticsOn()).toBe(true);
  });

  it("loads from Cloudflare over https", () => {
    expect(BEACON).toMatch(/^https:\/\/static\.cloudflareinsights\.com\//);
  });
});
