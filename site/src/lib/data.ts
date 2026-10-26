// Reading the exported data files while the site is built (`traceconomics export site --out site/public/data`).
// Pages put the numbers they show into the HTML, so nothing depends on a script to read them.

import fs from "node:fs";
import path from "node:path";

// Relative to the site folder, where `npm run build` runs: pages run from a bundled copy during
// the build, so a path relative to this file would point elsewhere.
export const DATA_ROOT = path.join(process.cwd(), "public", "data", "v1");

/** A country's current release of the inflation-by-group files, relative to DATA_ROOT. */
export const m1Dir = (country: string) => `${country}/m1/latest`;

export function readJson<T = any>(rel: string): T {
  const file = path.join(DATA_ROOT, rel);
  if (!fs.existsSync(file)) {
    throw new Error(`Missing ${file}: run "python -m traceconomics export site --out site/public/data" first.`);
  }
  return JSON.parse(fs.readFileSync(file, "utf-8"));
}

export interface GroupSeries {
  unit: string;
  index: (number | null)[];
  rch_a: (number | null)[];
  rch_m: (number | null)[];
  avg: Record<string, number>;
  se_a: (number | null)[];
  se_avg: Record<string, number>;
}

export interface SeriesFile {
  setting: Record<string, string>;
  start: string;
  end: string;
  flags: { code: string; index_to: string; rch_a_to: string; rch_m_to: string; avg_to: string }[];
  groups: Record<string, GroupSeries>;
  gaps: Record<string, { rch_a: (number | null)[]; avg: Record<string, number>; se_a: (number | null)[]; se_avg: Record<string, number> }>;
  footnotes: Record<string, Record<string, any>>;
}

export interface Settings {
  options: Record<string, string[]>;
  default: string;
  settings: (Record<string, string> & { slug: string; default: boolean })[];
}

export const settings = (country: string) => readJson<Settings>(`${m1Dir(country)}/settings.json`);
export const series = (country: string, slug: string) => readJson<SeriesFile>(`${m1Dir(country)}/series/${slug}.json`);
export const availability = (country: string) => readJson<any>(`${m1Dir(country)}/availability.json`);
export const calculator = (country: string) => readJson<any>(`${m1Dir(country)}/calculator.json`);
export const labels = () => readJson<{ labels: Record<string, { en: string; el: string; kind: string | null }> }>("labels/coicop18.json");

/** The month axis of a series file. */
export function months(file: { start: string; end: string }): string[] {
  const out: string[] = [];
  let y = Number(file.start.slice(0, 4));
  let m = Number(file.start.slice(5, 7));
  while (true) {
    const p = `${y}-${String(m).padStart(2, "0")}`;
    if (p > file.end) break;
    out.push(p);
    if (++m > 12) { m = 1; y++; }
  }
  return out;
}

/** The last month with a value, and the value. */
export function latest(values: (number | null)[], axis: string[]): { period: string; value: number } | null {
  for (let i = values.length - 1; i >= 0; i--) {
    if (values[i] !== null) return { period: axis[i], value: values[i] as number };
  }
  return null;
}
