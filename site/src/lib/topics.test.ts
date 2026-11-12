import { afterEach, describe, expect, it } from "vitest";
import { analyticsOn, BEACON } from "./analytics";
import { flag } from "./flags";
import { GLOSSARY_CATEGORIES } from "./glossary";
import {
  countries,
  countryHref,
  countryPaths,
  dataCountries,
  dataHref,
  m1Text,
  OFFICES,
  officialSources,
  topic,
  topicHref,
  topicPath,
  TOPICS,
} from "./topics";

describe("topics", () => {
  it(
    "each have a unique slug, and live ones cover at least one country",
    {
      meta: {
        id: "VT-TOPICS-001",
        given: "the list of topics",
        when: "it is checked",
        then: ["no two topics share a slug", "every live topic covers at least one country"],
      },
    },
    () => {
      expect(new Set(TOPICS.map((x) => x.slug)).size).toBe(TOPICS.length);
      for (const x of TOPICS.filter((x) => x.status === "live"))
        expect(x.countries.length).toBeGreaterThan(0);
    },
  );

  it(
    "are found by slug, or refused",
    {
      meta: {
        id: "VT-TOPICS-002",
        given: "a known topic slug and an unknown one",
        when: "each is looked up",
        then: [
          "inflation-by-group is found, with status live",
          'the unknown slug throws a "no topic" error',
        ],
      },
    },
    () => {
      expect(topic("inflation-by-group").status).toBe("live");
      expect(() => topic("no-such-topic")).toThrow(/no topic/);
    },
  );

  it(
    "give addresses only for pages that exist",
    {
      meta: {
        id: "VT-TOPICS-003",
        given: "the live topic inflation-by-group and a planned topic",
        when: "page addresses are asked for",
        then: [
          "the topic's page is /en/inflation-by-group/",
          "its Greek page for Greece is /el/gr/inflation-by-group/",
          "its explore section and its nested method section have addresses under Greece's page",
          'the planned topic\'s address throws a "planned" error',
          'an unknown country throws a "no page for \\"zz\\"" error',
          'an unknown section throws a "no section" error',
        ],
      },
    },
    () => {
      expect(topicHref("en", "inflation-by-group")).toBe("/en/inflation-by-group/");
      expect(topicHref("el", "inflation-by-group", "gr")).toBe("/el/gr/inflation-by-group/");
      expect(topicHref("en", "inflation-by-group", "gr", "explore")).toBe(
        "/en/gr/inflation-by-group/explore/",
      );
      expect(topicHref("en", "inflation-by-group", "gr", "method/weights-timing")).toBe(
        "/en/gr/inflation-by-group/method/weights-timing/",
      );
      const planned = TOPICS.find((x) => x.status === "planned")!;
      expect(() => topicHref("en", planned.slug)).toThrow(/planned/);
      expect(() => topicHref("en", "inflation-by-group", "zz")).toThrow(/no page for "zz"/);
      expect(() => topicHref("en", "inflation-by-group", "gr", "nope")).toThrow(/no section/);
    },
  );

  it(
    "give the path inside a language",
    {
      meta: {
        id: "VT-TOPICS-004",
        given: "the topic inflation-by-group",
        when: "its path inside a language is asked for, alone, with a country, and with a country and a section",
        then: [
          "alone it is the topic's slug",
          "with a country it is the country, then the slug",
          "with a section the section follows",
        ],
      },
    },
    () => {
      expect(topicPath("inflation-by-group")).toBe("inflation-by-group");
      expect(topicPath("inflation-by-group", "gr")).toBe("gr/inflation-by-group");
      expect(topicPath("inflation-by-group", "gr", "explore")).toBe(
        "gr/inflation-by-group/explore",
      );
    },
  );

  it(
    "build one page per language and country",
    {
      meta: {
        id: "VT-TOPICS-005",
        given: "the topic inflation-by-group and two languages",
        when: "its country pages are listed",
        then: [
          "there are two pages per country the topic covers",
          "the English page for Greece is among them",
        ],
      },
    },
    () => {
      const paths = countryPaths("inflation-by-group", ["el", "en"]);
      expect(paths).toHaveLength(2 * topic("inflation-by-group").countries.length);
      expect(paths).toContainEqual({ params: { lang: "en", country: "gr" } });
    },
  );
});

describe("countries", () => {
  it(
    "are the live topics' countries, as two-letter codes",
    {
      meta: {
        id: "VT-TOPICS-006",
        given: "the live topics",
        when: "their countries are listed",
        then: [
          "Greece (gr) is among them",
          "every country is two lowercase letters",
          "the countries with data are the same list",
        ],
      },
    },
    () => {
      expect(countries()).toContain("gr");
      for (const c of countries()) expect(c).toMatch(/^[a-z]{2}$/);
      expect(dataCountries()).toEqual(countries());
    },
  );

  it(
    "have a page and a data page, and an unknown one has neither",
    {
      meta: {
        id: "VT-TOPICS-007",
        given: "Greece and an unknown country",
        when: "their page and data page addresses are asked for",
        then: [
          "Greece's page is /en/gr/",
          "the data index is /en/data/ and Greece's Greek data page is /el/data/gr/",
          "the unknown country's page and data page each throw an error",
        ],
      },
    },
    () => {
      expect(countryHref("en", "gr")).toBe("/en/gr/");
      expect(dataHref("en")).toBe("/en/data/");
      expect(dataHref("el", "gr")).toBe("/el/data/gr/");
      expect(() => countryHref("en", "zz")).toThrow();
      expect(() => dataHref("en", "zz")).toThrow();
    },
  );

  it(
    "each have a statistics office, then Eurostat",
    {
      meta: {
        id: "VT-TOPICS-008",
        given: "the countries with data",
        when: "their official sources are listed",
        then: [
          "the last source is Eurostat",
          "there is one source per country with data, plus Eurostat",
          "each country's source is its own office, in the countries' order, and no two are the same",
          "Greece's office is ELSTAT",
        ],
      },
    },
    () => {
      const sources = officialSources();
      expect(sources.at(-1)!.key).toBe("eurostat");
      expect(sources).toHaveLength(dataCountries().length + 1);
      const offices = sources.slice(0, -1);
      offices.forEach((office, i) => expect(office).toBe(OFFICES[dataCountries()[i]]));
      expect(offices.map((o) => o.key)).not.toContain("eurostat");
      expect(new Set(offices.map((o) => o.key)).size).toBe(offices.length);
      expect(offices[dataCountries().indexOf("gr")].key).toBe("elstat");
    },
  );

  it(
    "each have a flag, drawn as a hidden SVG; a country without one stops the build",
    {
      meta: {
        id: "VT-TOPICS-009",
        given: "every listed country and an unknown one",
        when: "their flags are drawn",
        then: [
          'each listed country\'s flag is a complete SVG element marked aria-hidden="true"',
          'the unknown country throws a "no flag" error',
        ],
      },
    },
    () => {
      for (const c of countries()) {
        const svg = flag(c);
        expect(svg).toMatch(/^<svg [^>]*aria-hidden="true"/);
        expect(svg).toMatch(/<\/svg>$/);
      }
      expect(() => flag("zz")).toThrow(/no flag/);
    },
  );

  it(
    "have their own written texts, never Greece's borrowed",
    {
      meta: {
        id: "VT-TOPICS-010",
        given: "Greece and an unknown country",
        when: "their method text is asked for in English",
        then: [
          "Greece's is en/method",
          "the unknown country's throws an error saying it must write its own",
        ],
      },
    },
    () => {
      expect(m1Text("gr", "en", "method")).toBe("en/method");
      expect(() => m1Text("zz", "en", "method")).toThrow(/write its own/);
    },
  );
});

describe("the glossary's categories", () => {
  it(
    "are distinct",
    {
      meta: {
        id: "VT-TOPICS-011",
        given: "the glossary's categories",
        when: "they are listed",
        then: "no category appears twice",
      },
    },
    () => {
      expect(new Set(GLOSSARY_CATEGORIES).size).toBe(GLOSSARY_CATEGORIES.length);
    },
  );
});

describe("the visit counter", () => {
  const before = process.env.TRACECONOMICS_ANALYTICS;
  afterEach(() => {
    if (before === undefined) delete process.env.TRACECONOMICS_ANALYTICS;
    else process.env.TRACECONOMICS_ANALYTICS = before;
  });

  it(
    "is on only in release builds",
    {
      meta: {
        id: "VT-TOPICS-012",
        given: "the TRACECONOMICS_ANALYTICS environment variable",
        when: 'the visit counter is asked whether it is on, with the variable unset, set to "yes", then set to "on"',
        then: [
          "it is off when the variable is unset",
          'it is off when the variable is "yes"',
          'it is on when the variable is "on"',
        ],
      },
    },
    () => {
      delete process.env.TRACECONOMICS_ANALYTICS;
      expect(analyticsOn()).toBe(false);
      process.env.TRACECONOMICS_ANALYTICS = "yes";
      expect(analyticsOn()).toBe(false);
      process.env.TRACECONOMICS_ANALYTICS = "on";
      expect(analyticsOn()).toBe(true);
    },
  );

  it(
    "loads from Cloudflare over https",
    {
      meta: {
        id: "VT-TOPICS-013",
        given: "the visit counter's beacon address",
        when: "it is read",
        then: "it is an https address on static.cloudflareinsights.com",
      },
    },
    () => {
      expect(BEACON).toMatch(/^https:\/\/static\.cloudflareinsights\.com\//);
    },
  );
});
