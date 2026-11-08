// Words for the consistency topic's pages: a period, a list of causes, a difference.
import { num } from "./format";
import { has, month, t, type Lang } from "./i18n";
import type { Category, Check } from "./m5";

/** "YYYY-MM" as a month; "YYYY/<group>" as the year and the group's name where the site has one. */
export function periodLabel(lang: Lang, period: string): string {
  if (/^\d{4}-\d{2}$/.test(period)) return month(lang, period);
  const [year, group] = period.split("/");
  if (!group) return year;
  for (const key of [`group.hhtype/${group}`, `group.B/${group}`]) if (has(lang, key)) return `${year} · ${t(lang, key)}`;
  return `${year} · ${group}`;
}

/** "7 rounding, 1 a revision not carried through", in the categories' fixed order. */
export function causes(lang: Lang, c: Check): string {
  const order: Category[] = ["rounding", "revision", "rebasing", "splice", "definition", "not-known"];
  return order.filter((k) => c.differ[k]).map((k) => `${c.differ[k]} ${t(lang, `m5.cat.${k}`)}`).join(", ");
}

/** A difference in the check's unit: percentage points to four decimals, shares to two. */
export const diff = (lang: Lang, value: number) => `${value > 0 ? "+" : ""}${num(lang, value, Math.abs(value) < 0.01 ? 4 : 2)}`;
