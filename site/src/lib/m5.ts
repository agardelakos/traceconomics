// The consistency topic's data (`traceconomics module5 run`, exported to /data/v1/{country}/m5/latest/):
// each check of an official figure against its own inputs, and each question several sources answer.
// Read while the site is built; pages put every number in the HTML.

import { readJson } from "./data";

export const m5Dir = (country: string) => `${country}/m5/latest`;

export type Category = "rounding" | "revision" | "rebasing" | "splice" | "definition" | "not-known";

export interface Difference {
  period: string;
  published: number;
  rebuilt: number;
  difference: number;
  explanation: Category;
  finding: string;
}

export interface Check {
  id: string;
  country: string;
  unit: string;
  tolerance: number;
  published: { source: string; reference: string; label: string };
  rebuilt: { source: string; reference: string; label: string };
  first: string | null;
  last: string | null;
  compared: number;
  agree: number;
  by_year: Record<string, { compared: number; agree: number }>;
  differ: Partial<Record<Category, number>>;
  differences: Difference[];
  extra?: Record<string, Record<string, number | string>>;
}

export interface Question {
  id: string;
  country: string;
  unit: string;
  sources: { label: string; source: string; reference: string; more?: string[]; definition: string }[];
  first: string | null;
  last: string | null;
  values: Record<string, Record<string, number | null>>;
}

export interface Results { format: string; country: string; licence: string; attribution: string; checks: Check[]; questions: Question[] }

export function results(country: string): Results {
  const r = readJson<Results>(`${m5Dir(country)}/checks.json`);
  if (r.format !== "m5-v1" || r.country !== country) throw new Error(`${m5Dir(country)}/checks.json is not module5's results for ${country}`);
  return { ...r, questions: r.questions ?? [] };
}

// Where a question's line comes from, as its card's chip names it: the kind of source and who we
// take the figures from (as the Sources list and the reuse notices name them).
const CHIPS: [RegExp, string][] = [
  [/^eurostat:cens_/, "census-eurostat"], [/^oet-local:silc_/, "silc-elstat"], [/^eurostat:ilc_/, "silc-eurostat"],
  [/^oet-local:hbs_/, "hbs-elstat"], [/^eurostat:(nama|nasa)_/, "na-eurostat"], [/^aade:/, "tax-aade"],
  [/^eurostat:une_/, "lfs-eurostat"], [/^ec-empl:/, "register-ec"], [/^elstat:cpi/, "cpi-elstat"], [/^eurostat:prc_hicp/, "hicp-eurostat"],
];

/** A question's chips, one per kind of source, in the order of its lines (the key under `m5.chip.`). */
export function chips(q: Question): string[] {
  return [...new Set(q.sources.map((s) => {
    const hit = CHIPS.find(([re]) => re.test(s.source));
    if (!hit) throw new Error(`${q.id}: no chip for source "${s.source}"`);
    return hit[1];
  }))];
}

// The order checks are shown in: explained first (a difference found and its cause shown is the
// topic's work at its most useful), then partly explained, then those whose cause isn't known
// yet, then the consistent ones. Within a status, file order.
export const STATUS_ORDER: Status[] = ["explained", "partly", "unknown", "agree"];

export function ordered(checks: Check[]): Check[] {
  return STATUS_ORDER.flatMap((st) => checks.filter((c) => status(c) === st));
}

// The glossary term for what a check is about, by the source of its published side.
const TERMS: [RegExp, string][] = [[/^elstat:cpi/, "consumer-price-index"], [/^eurostat:prc_hicp/, "hicp"], [/^elstat:hbs/, "household-budget-survey"]];

/** The glossary term a check's card explains, if any. */
export function termOf(c: Pick<Check, "published">): string | undefined {
  return TERMS.find(([re]) => re.test(c.published.source))?.[1];
}

/**
 * What a check compared, year by year, with runs of years where everything agrees joined into one
 * row ("1960–2000: 492 of 492"), so a long clean history reads in a line and every year that
 * differs stands on its own.
 */
export function yearRuns(byYear: Check["by_year"]): { from: string; to: string; compared: number; agree: number }[] {
  const out: { from: string; to: string; compared: number; agree: number }[] = [];
  for (const year of Object.keys(byYear).sort()) {
    const { compared, agree } = byYear[year];
    const last = out[out.length - 1];
    const clean = agree === compared;
    if (last && clean && last.agree === last.compared && Number(year) === Number(last.to) + 1) {
      last.to = year; last.compared += compared; last.agree += agree;
    } else out.push({ from: year, to: year, compared, agree });
  }
  return out;
}

/** How many of a consistent check's figures differ only by rounding (0 when every one agrees). */
export function roundingOnly(c: Pick<Check, "differ" | "compared" | "agree">): number {
  return status(c) === "agree" ? c.compared - c.agree : 0;
}

/** A check's or question's address within the topic: its id without the country's prefix. */
export function slugOf(id: string, country: string): string {
  if (!id.startsWith(`${country}-`)) throw new Error(`"${id}" doesn't start with "${country}-"`);
  return id.slice(country.length + 1);
}

/**
 * Where a check stands, from its differences only: consistent when every period agrees or differs
 * only by rounding (published figures are rounded, so a last-digit gap isn't an inconsistency;
 * the page says so in a note); explained when every difference has another known cause too;
 * partly; not known. Never "wrong": the topic says two published numbers are inconsistent, not
 * that someone erred.
 */
export type Status = "agree" | "explained" | "partly" | "unknown";
export function status(c: Pick<Check, "differ" | "compared" | "agree">): Status {
  const unknown = c.differ["not-known"] ?? 0;
  const differ = c.compared - c.agree;
  if (differ === (c.differ.rounding ?? 0)) return "agree";
  if (unknown === 0) return "explained";
  return unknown < differ ? "partly" : "unknown";
}

/** Findings with their own page: the differences an explanation names a page for, one per page. */
export function findings(c: Check): { slug: string; periods: string[]; explanation: Category }[] {
  const by = new Map<string, { slug: string; periods: string[]; explanation: Category }>();
  for (const d of c.differences) {
    if (!d.finding) continue;
    const f = by.get(d.finding) ?? { slug: d.finding, periods: [], explanation: d.explanation };
    f.periods.push(d.period);
    by.set(d.finding, f);
  }
  return [...by.values()];
}
