// The parity test: the browser's calculator, run on every preset with nothing changed, must give
// back the official series to the last published digit, so the calculator and the charts can
// never disagree. It reads the files the pipeline exported (`traceconomics export site`); without them it
// fails, because a skipped parity test proves nothing.

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { annualAverageRate, annualRate, chain, monthlyRate, published, type CalculatorData } from "./calculator";
import { fixed } from "./round";

const latest = resolve(__dirname, "../../../public/data/v1/gr/m1/latest");
const calcPath = resolve(latest, "calculator.json");
const seriesPath = resolve(latest, "series/purchases_excluded_cpi_N_priced.json");

interface SeriesFile {
  start: string;
  groups: Record<string, { index: (number | null)[]; rch_a: (number | null)[]; rch_m: (number | null)[]; avg: Record<string, number> }>;
}

function axis(start: string, n: number): string[] {
  const out: string[] = [];
  let y = Number(start.slice(0, 4));
  let m = Number(start.slice(5, 7));
  for (let i = 0; i < n; i++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    if (++m > 12) { m = 1; y++; }
  }
  return out;
}

describe("calculator parity with the published series", () => {
  it("has the exported files", () => {
    expect(existsSync(calcPath) && existsSync(seriesPath),
      `missing ${calcPath} or ${seriesPath}: run "python -m traceconomics export site --out site/public/data" first`).toBe(true);
  });

  if (!existsSync(calcPath) || !existsSync(seriesPath)) return;
  const data: CalculatorData = JSON.parse(readFileSync(calcPath, "utf-8"));
  const series: SeriesFile = JSON.parse(readFileSync(seriesPath, "utf-8"));
  const from = `${data.first_year}-01`;

  for (const preset of Object.keys(data.presets)) {
    it(`${preset}: index, annual, monthly and annual-average rates match`, () => {
      const g = series.groups[preset];
      expect(g, `no ${preset} in the series file`).toBeDefined();
      const ours = published(chain(data, preset));
      const months = axis(series.start, g.index.length);
      let compared = 0;
      months.forEach((p, i) => {
        if (p < from || g.index[i] === null) return;
        expect(ours.get(p), `${preset} index ${p}`).toBe(g.index[i]);
        compared++;
        const a = annualRate(ours, p);
        if (a !== null && g.rch_a[i] !== null) expect(Number(fixed(a, 1)), `${preset} annual rate ${p}`).toBe(g.rch_a[i]);
        const m = monthlyRate(ours, p);
        if (m !== null && g.rch_m[i] !== null) expect(Number(fixed(m, 1)), `${preset} monthly rate ${p}`).toBe(g.rch_m[i]);
      });
      expect(compared).toBeGreaterThan(80);
      for (const [year, v] of Object.entries(g.avg)) {
        const r = annualAverageRate(ours, Number(year));
        if (r !== null) expect(Number(fixed(r, 1)), `${preset} annual average ${year}`).toBe(v);
      }
    });
  }
});
