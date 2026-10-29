// What the site covers: its countries, the topics each one has, and every page's address.
//
// Addresses never change once published, so they are built here and nowhere else:
//
//   /{lang}/                                   the site's home: every country, every topic
//   /{lang}/{country}/                         a country: every topic it has, and what is coming
//   /{lang}/{country}/{topic}/                 a topic for one country: the headline figures
//   /{lang}/{country}/{topic}/{section}/...    its pages (explore, calculator, method)
//   /{lang}/{topic}/                           a topic across countries: what it is, who has it
//   /{lang}/data/  ·  /{lang}/data/{country}/  every file, by country, grouped by topic on the page
//   /{lang}/glossary/ · /about/                pages for the whole site
//
// The country comes first because most readers come for one country: they read its language,
// follow its releases and want every topic it has. A topic still has its own page, above the
// countries, for readers who compare countries; some topics (forecast scores, revisions) compare
// well, others need each country's own survey. Countries are two-letter codes and every other
// first-level name (topics, data, glossary, about) is longer, so the two can never clash.
// A planned topic or country has no page and no address yet: it gets one when there is something
// to show. Planned ones aren't named on the site, except a topic marked `shown`: a greyed card,
// "coming soon", with its question. The rest hide behind one small "more topics" card.

import { href, type Lang } from "./i18n";

export type Status = "live" | "planned";

export interface Topic {
  slug: string;              // in the address, the same in every language
  module: string;            // its folder in the published data: /data/v1/{country}/{module}/
  status: Status;
  countries: string[];       // ISO 3166-1 alpha-2, lower case, with a page for this topic
  sections: string[];        // the pages each country has, in menu order ("" is its overview)
  shown?: boolean;           // a planned topic named on the site as "coming soon" (topic cards only)
}

export const TOPICS: Topic[] = [
  {
    slug: "inflation-by-group", module: "m1", status: "live", countries: ["gr"],
    // In reading order: what it is, how it was measured, who the groups are, then the tools.
    sections: ["", "method", "groups", "explore", "calculator"],
  },
  { slug: "official-figures-checked", module: "m5", status: "planned", countries: [], sections: [], shown: true },
  { slug: "forecast-scorecard", module: "m2", status: "planned", countries: [], sections: [] },
  { slug: "gdp-nowcast", module: "m3", status: "planned", countries: [], sections: [] },
  { slug: "revisions", module: "m4", status: "planned", countries: [], sections: [] },
];

// The official sources the footer names: each covered country's statistics office, then Eurostat.
// Each links to the publisher's own home page, in the reader's language where it has one.
// `shown`: the address written out as the link's text, for a publisher whose reuse terms ask that
// links to it name its website in full (ELSTAT: www.statistics.gr).
export interface Office { key: string; href: Record<Lang, string>; shown?: string }
export const OFFICES: Record<string, Office> = {
  gr: { key: "elstat", href: { en: "https://www.statistics.gr/en/home", el: "https://www.statistics.gr/el/home" }, shown: "www.statistics.gr" },
};
export const EUROSTAT: Office = { key: "eurostat", href: { en: "https://ec.europa.eu/eurostat", el: "https://ec.europa.eu/eurostat" } };

/** Every source the site's live pages are built from: the covered countries' offices, then Eurostat. */
export function officialSources(): Office[] {
  return [...dataCountries().map((c) => {
    if (!OFFICES[c]) throw new Error(`no statistics office listed for "${c}"`);
    return OFFICES[c];
  }), EUROSTAT];
}

export function topic(slug: string): Topic {
  const found = TOPICS.find((x) => x.slug === slug);
  if (!found) throw new Error(`no topic "${slug}"`);
  return found;
}

/** The address of a topic's page: its page across countries, or one country's overview or page. */
export function topicHref(lang: Lang, slug: string, country?: string, section = ""): string {
  const tp = topic(slug);
  if (tp.status !== "live") throw new Error(`topic "${slug}" is planned: it has no page yet`);
  if (country === undefined) return href(lang, slug);
  if (!tp.countries.includes(country)) throw new Error(`topic "${slug}" has no page for "${country}"`);
  if (!tp.sections.includes(section.split("/")[0])) throw new Error(`topic "${slug}" has no section "${section}"`);
  return href(lang, topicPath(slug, country, section));
}

/** The path inside a language (no /{lang}/), as the layout needs it for the language switch. */
export function topicPath(slug: string, country?: string, section = ""): string {
  return (country === undefined ? [slug] : [country, slug, section]).filter(Boolean).join("/");
}

/** The countries with pages: every country a live topic covers, in the order first listed. */
export function countries(): string[] {
  const found = [...new Set(TOPICS.filter((x) => x.status === "live").flatMap((x) => x.countries))];
  for (const c of found) if (!/^[a-z]{2}$/.test(c)) throw new Error(`country "${c}" is not a two-letter code`);
  return found;
}

/** A country's page: every topic it has. */
export function countryHref(lang: Lang, country: string): string {
  if (!countries().includes(country)) throw new Error(`no page for country "${country}"`);
  return href(lang, country);
}

/**
 * The countries with a data page: every country a live topic covers. Data are by country first
 * (as the published files are: /data/v1/{country}/{module}/), because a reader who wants data
 * wants all of a country's; the page groups them by topic. `eu` is kept for EU-wide results, if
 * a module ever computes them; it is not for copies of Eurostat's own tables.
 */
export function dataCountries(): string[] {
  return countries();
}

/** The site's data pages: the hub, or one country's page. */
export function dataHref(lang: Lang, country?: string): string {
  if (country === undefined) return href(lang, "data");
  if (!dataCountries().includes(country)) throw new Error(`no data page for "${country}"`);
  return href(lang, `data/${country}`);
}

/** getStaticPaths for a topic's per-country pages: every language × every country it covers. */
export function countryPaths(slug: string, langs: readonly Lang[]) {
  return langs.flatMap((lang) => topic(slug).countries.map((country) => ({ params: { lang, country } })));
}

/**
 * The content entry (src/content/<collection>/<lang>/<id>.md) holding a country's written text
 * for inflation by group: method and data. Those texts are Greece's (they name its sources and
 * options), so another country must bring its own before it is listed, never borrow Greece's.
 */
export function m1Text(country: string, lang: Lang, id: string): string {
  if (country !== "gr") throw new Error(`no inflation-by-group texts for "${country}": write its own method and data pages first`);
  return `${lang}/${id}`;
}
