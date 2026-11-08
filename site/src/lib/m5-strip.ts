// The third row of the bar on the consistency topic's inner pages: every check, or every question,
// by its short name (`m5.short.<id>`), the one being read marked current. Checks in the overview's
// order, questions in file order, so the row matches the lists a reader came from.
import { t, type Lang } from "./i18n";
import { ordered, results, slugOf } from "./m5";
import { topicHref, type Strip } from "./topics";

const SLUG = "official-figures-consistency";

export function checkStrip(lang: Lang, country: string, current: string): Strip {
  return { label: t(lang, "m5.strip.checks"), items: ordered(results(country).checks).map((c) => ({
    href: topicHref(lang, SLUG, country, `checks/${slugOf(c.id, country)}`), label: t(lang, `m5.short.${c.id}`), current: c.id === current })) };
}

export function questionStrip(lang: Lang, country: string, current: string): Strip {
  return { label: t(lang, "m5.strip.questions"), items: results(country).questions.map((q) => ({
    href: topicHref(lang, SLUG, country, `same-question/${slugOf(q.id, country)}`), label: t(lang, `m5.short.${q.id}`), current: q.id === current })) };
}
