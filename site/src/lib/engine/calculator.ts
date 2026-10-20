// The personal calculator: a household's own index, from the published calculator file.
//
// The file (`calculator.json`, written by the pipeline) holds, for each preset household group
// and year, the weights the official series used, summed by the index that prices them; and,
// for each year, every such index's price ratios to the December before. The official index for
// a month is the weighted average of those ratios times the index of that December. This module
// does that and nothing else: every method choice was made upstream.
//
// A user's basket changes how much goes to each division (food, housing, ...). Inside a
// division, each year keeps the preset's own mix, scaled to the user's division share. Left
// untouched, the result is the preset's official index exactly; the parity test checks that.
//
// The arithmetic follows the pipeline's reference implementation step for step, including the
// order of the sums, so the floating-point results agree.

import { roundHalfEven } from "./round";

export interface CalculatorData {
  base_year: number;
  first_year: number;
  digits: number;
  codes: string[];
  ratios: Record<string, [number, (number | null)[]][]>;
  presets: Record<string, Record<string, [number, number][]>>;
}

export type YearWeights = Map<string, number>;          // pricing code -> weight
export type Shares = Record<string, number>;            // division ("01" ... "13") -> share, summing to 1
export type Index = Map<string, number>;                // "YYYY-MM" -> value

export const division = (code: string): string => code.slice(0, 2);

function linkMonth(year: number): string {
  return `${year - 1}-12`;
}

function month(year: number, m: number): string {
  return `${year}-${String(m + 1).padStart(2, "0")}`;
}

/** {year: {pricing code: weight}} for a preset, as published. */
export function presetWeights(data: CalculatorData, preset: string): Map<number, YearWeights> {
  const years = data.presets[preset];
  if (!years) throw new Error(`no preset ${preset}`);
  const out = new Map<number, YearWeights>();
  for (const [year, rows] of Object.entries(years)) {
    out.set(Number(year), new Map(rows.map(([i, w]) => [data.codes[i], w])));
  }
  return out;
}

/** Each division's share of a year's weights. */
export function divisionShares(weights: YearWeights): Shares {
  let total = 0;
  const out: Shares = {};
  for (const [code, w] of weights) {
    out[division(code)] = (out[division(code)] ?? 0) + w;
    total += w;
  }
  for (const d of Object.keys(out)) out[d] /= total;
  return out;
}

/** A year's weights with the user's division shares, each division keeping the year's own mix.
 *  A division the preset didn't buy from that year has no mix to scale; its share is left out
 *  and the rest count proportionally more (a weighted average needs no rescaling). */
export function withShares(weights: YearWeights, shares: Shares): YearWeights {
  const own = divisionShares(weights);
  const out: YearWeights = new Map();
  for (const [code, w] of weights) {
    const d = division(code);
    const target = shares[d] ?? 0;
    out.set(code, own[d] > 0 ? (w / own[d]) * target : 0);
  }
  return out;
}

/** The index, base year = 100, unrounded. `shares`, if given, applies to every year. */
export function chain(data: CalculatorData, preset: string, shares?: Shares): Index {
  const weightsByYear = presetWeights(data, preset);
  const index: Index = new Map([[linkMonth(data.first_year), 100]]);
  for (let year = data.first_year; weightsByYear.has(year); year++) {
    const base = index.get(linkMonth(year));
    if (base === undefined) break;
    const raw = weightsByYear.get(year)!;
    const w = shares ? withShares(raw, shares) : raw;
    const ratios = new Map(data.ratios[String(year)].map(([i, values]) => [data.codes[i], values]));
    const codes = [...w.keys()].sort();             // the reference sums in code order
    const months = Math.max(...codes.map((c) => ratios.get(c)?.length ?? 0));
    for (let m = 0; m < months; m++) {
      let num = 0;
      let den = 0;
      for (const code of codes) {
        const v = ratios.get(code)?.[m];
        if (v === null || v === undefined) continue;
        num += w.get(code)! * v;
        den += w.get(code)!;
      }
      if (den) index.set(month(year, m), base * (num / den));
    }
  }
  return rebase(index, data.base_year);
}

export function rebase(index: Index, year: number): Index {
  const values = Array.from({ length: 12 }, (_, m) => index.get(month(year, m)));
  if (values.some((v) => v === undefined)) throw new Error(`no complete year ${year} to rebase on`);
  const avg = (values as number[]).reduce((a, b) => a + b, 0) / 12;
  return new Map([...index].map(([p, v]) => [p, (v / avg) * 100]));
}

/** The published index: two decimals. */
export function published(index: Index): Index {
  return new Map([...index].map(([p, v]) => [p, roundHalfEven(v, 2)]));
}

function shift(period: string, months: number): string {
  const total = Number(period.slice(0, 4)) * 12 + Number(period.slice(5, 7)) - 1 + months;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

/** Change on the same month a year earlier, in percent, from the published (rounded) index. */
export function annualRate(index: Index, period: string): number | null {
  const cur = index.get(period);
  const prev = index.get(shift(period, -12));
  return cur === undefined || prev === undefined ? null : (cur / prev - 1) * 100;
}

export function monthlyRate(index: Index, period: string): number | null {
  const cur = index.get(period);
  const prev = index.get(shift(period, -1));
  return cur === undefined || prev === undefined ? null : (cur / prev - 1) * 100;
}

export function annualAverageRate(index: Index, year: number): number | null {
  const avg = (y: number) => {
    const v = Array.from({ length: 12 }, (_, m) => index.get(month(y, m)));
    return v.some((x) => x === undefined) ? null : (v as number[]).reduce((a, b) => a + b, 0) / 12;
  };
  const cur = avg(year);
  const prev = avg(year - 1);
  return cur === null || prev === null ? null : (cur / prev - 1) * 100;
}
