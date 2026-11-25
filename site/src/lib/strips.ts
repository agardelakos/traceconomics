// The bar's third row ("the strip"): on a page inside a section (a method option, a check, a
// question), every page of that section by its short name, the one being read marked current.
//
// The rows come from here, never from the pages: a section with pages of its own is declared in
// `topics.ts` (`inner`) and gets its row from `SOURCES` below, and the layout builds the strip
// from the page's address. So a new check, question or option gets its strip without anyone
// remembering to pass one, and a page inside a section that has no row fails the build.
import { t, type Lang } from "./i18n";
import { ordered, results, slugOf } from "./m5";
import { m1Text, topic, topicHref, type Strip } from "./topics";

/** One page in a strip, before the current one is marked. */
export interface Row {
  href: string;
  label: string;
}

interface Source {
  label: (lang: Lang) => string;
  rows: (lang: Lang, country: string) => Row[] | Promise<Row[]>;
}

const M1 = "inflation-by-group";
const M5 = "official-figures-consistency";

/** Each section with pages of its own, keyed `<topic>/<section>`, and how its row is listed. */
export const SOURCES: Record<string, Source> = {
  // The method's options, in the method page's order.
  [`${M1}/method`]: {
    label: (lang) => t(lang, "method.options"),
    rows: async (lang, country) => {
      // Loaded only when the site is built: the content collections don't exist in unit tests.
      const { getCollection } = await import("astro:content");
      const options = await getCollection(
        "method",
        (e) => Boolean(e.data.option) && e.id.startsWith(m1Text(country, lang, "")),
      );
      return options
        .sort((a, b) => a.data.order - b.data.order)
        .map((e) => ({
          href: topicHref(lang, M1, country, `method/${e.id.split("/")[1]}`),
          label: e.data.title,
        }));
    },
  },
  // Every check by its short name, in the overview's order, so the row matches the list a reader
  // came from.
  [`${M5}/checks`]: {
    label: (lang) => t(lang, "m5.strip.checks"),
    rows: (lang, country) =>
      ordered(results(country).checks).map((c) => ({
        href: topicHref(lang, M5, country, `checks/${slugOf(c.id, country)}`),
        label: t(lang, `m5.short.${c.id}`),
      })),
  },
  // Every question, in file order.
  [`${M5}/same-question`]: {
    label: (lang) => t(lang, "m5.strip.questions"),
    rows: (lang, country) =>
      results(country).questions.map((q) => ({
        href: topicHref(lang, M5, country, `same-question/${slugOf(q.id, country)}`),
        label: t(lang, `m5.short.${q.id}`),
      })),
  },
};

/**
 * The `SOURCES` key for a page of a topic, or undefined for a section's own page (no strip).
 * Throws for a page inside a section that isn't declared or has no row: that page would
 * otherwise go out without its strip.
 */
export function stripKey(slug: string, section: string): string | undefined {
  const [top, ...below] = section.split("/");
  if (below.length === 0) return undefined;
  const key = `${slug}/${top}`;
  if (!(topic(slug).inner ?? []).includes(top))
    throw new Error(
      `page "${section}" of topic "${slug}" is inside section "${top}", which topics.ts doesn't list in \`inner\``,
    );
  if (!SOURCES[key]) throw new Error(`section "${key}" has no row in lib/strips.ts (SOURCES)`);
  return key;
}

/**
 * Marks the page being read: the row whose address is the page's, or the page's parent (a
 * finding marks its check). Exactly one row must match.
 */
export function markCurrent(label: string, rows: Row[], page: string): Strip {
  const items = rows.map((r) => ({ ...r, current: page.startsWith(r.href) }));
  const marked = items.filter((i) => i.current).length;
  if (marked !== 1)
    throw new Error(`the strip "${label}" marks ${marked} rows current for ${page}, not one`);
  return { label, items };
}

/** The strip for a page of a topic for one country, or undefined where the page has none. */
export async function stripFor(
  lang: Lang,
  slug: string,
  country: string,
  section: string,
): Promise<Strip | undefined> {
  const key = stripKey(slug, section);
  if (key === undefined) return undefined;
  const source = SOURCES[key];
  const label = source.label(lang);
  return markCurrent(
    label,
    await source.rows(lang, country),
    topicHref(lang, slug, country, section),
  );
}
