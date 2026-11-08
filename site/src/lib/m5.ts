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

/** A check's or question's address within the topic: its id without the country's prefix. */
export function slugOf(id: string, country: string): string {
  if (!id.startsWith(`${country}-`)) throw new Error(`"${id}" doesn't start with "${country}-"`);
  return id.slice(country.length + 1);
}

/**
 * Where a check stands, from its differences only: every period agrees; every difference has a
 * known cause (rounding included); some do and some don't; none do. Never "wrong": the topic
 * says two published numbers are inconsistent, not that someone erred.
 */
export type Status = "agree" | "explained" | "partly" | "unknown";
export function status(c: Pick<Check, "differ" | "compared" | "agree">): Status {
  const unknown = c.differ["not-known"] ?? 0;
  const differ = c.compared - c.agree;
  if (differ === 0) return "agree";
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
