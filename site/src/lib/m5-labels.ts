// Words for the consistency topic's pages: a period, a list of causes, a difference.
import { num } from "./format";
import { has, month, t, type Lang } from "./i18n";
import type { Category, Check } from "./m5";

/** A band of the survey's table 1.03 as ELSTAT names it in English ("up 750 €", "751-1100 €",
 * "3501 and over €", "1 member", "6 members and over"), in the page's language. */
export function bandLabel(lang: Lang, band: string): string {
  if (lang === "en") return band;
  return band
    .replace(/^up /, "έως ")
    .replace(/ and over/, " και άνω")
    .replace(/\b1 member\b/, "1 μέλος")
    .replace(/ members\b/, " μέλη");
}

/** "YYYY-MM" as a month; "YYYY/<group>" as the year and the group's name where the site has one;
 * "YYYY/<column>/<code>" (the survey's spending table) as the year, the column and the item code. */
export function periodLabel(lang: Lang, period: string): string {
  if (/^\d{4}-\d{2}$/.test(period)) return month(lang, period);
  const [year, group, code] = period.split("/");
  if (code !== undefined)
    return `${year} · ${group === "all" ? t(lang, "m5.period.all") : bandLabel(lang, group)} · ${code}`;
  if (!group) return year;
  for (const key of [`group.hhtype/${group}`, `group.B/${group}`])
    if (has(lang, key)) return `${year} · ${t(lang, key)}`;
  return `${year} · ${group}`;
}

/** A check's first or last period, for its span: the year alone for the spending table's
 * "YYYY/<column>/<code>" (the column and the item would mean nothing there), else as `periodLabel`. */
export function spanLabel(lang: Lang, period: string): string {
  const parts = period.split("/");
  return parts.length === 3 ? parts[0] : periodLabel(lang, period);
}

/** The years a check actually compared ("checked 1960–2026"), from its data, never from a source's
 * own span: a source line saying "from 1959" would read as a claim about what was checked. */
export function checkedSpan(lang: Lang, c: Pick<Check, "by_year">): string {
  const years = Object.keys(c.by_year ?? {}).sort();
  if (years.length === 0) return "";
  const [from, to] = [years[0], years[years.length - 1]];
  return from === to
    ? t(lang, "m5.checked.one", { year: from })
    : t(lang, "m5.checked", { from, to });
}

/** "7 rounding, 1 a revision not carried through", in the categories' fixed order. */
export function causes(lang: Lang, c: Check): string {
  const order: Category[] = [
    "rounding",
    "revision",
    "rebasing",
    "splice",
    "definition",
    "not-known",
  ];
  return order
    .filter((k) => c.differ[k])
    .map((k) => `${c.differ[k]} ${t(lang, `m5.cat.${k}`)}`)
    .join(", ");
}

/** A difference in the check's unit: percentage points to four decimals, shares to two. */
export const diff = (lang: Lang, value: number) =>
  `${value > 0 ? "+" : ""}${num(lang, value, Math.abs(value) < 0.01 ? 4 : 2)}`;
