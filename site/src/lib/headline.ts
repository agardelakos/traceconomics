// The headline figures of the inflation-by-group topic for one country, as sentences use them:
// what a basket bought in a base month costs now for the poorest and the richest fifth, the year
// the two differed most, and food's share of each one's spending. Read from the default series and
// the calculator file at build time; a check fails the build if the data stop saying what the
// sentences say.

import { calculator, months, series, settings } from "./data";

// The month the euro example starts from: just before the 2021-2022 price surge.
export const BASE_MONTH = "2021-01";
export const BASE_AMOUNT = 100;
const SHOWN = ["B/Q1", "B/Q5"];

// The poorest group's index from the base month, as the points of a line in a 330×112 box: the
// faint line behind the home page's title. Decoration only, so no axes; it moves with the data.
export function bandLine(country: string): string {
  const s = series(country, settings(country).default);
  const values = s.groups[SHOWN[0]].index.slice(months(s).indexOf(BASE_MONTH)).filter((v): v is number => v !== null);
  const lo = Math.min(...values), hi = Math.max(...values);
  return values.map((v, i) => `${((i / (values.length - 1)) * 330).toFixed(1)},${(108 - ((v - lo) / (hi - lo)) * 104).toFixed(1)}`).join(" ");
}

export function headline(country: string) {
  const s = series(country, settings(country).default);
  const axis = months(s);

  // What the base month's shopping costs now: each group's chain-linked index, latest month over
  // the base month. The latest month is the last one every shown group has.
  const at = (g: string, p: string) => s.groups[g].index[axis.indexOf(p)];
  let last = axis.length - 1;
  while (last >= 0 && SHOWN.some((g) => s.groups[g].index[last] === null)) last--;
  const latestMonth = axis[last];
  const baskets = SHOWN.map((g) => {
    const from = at(g, BASE_MONTH);
    const to = s.groups[g].index[last];
    if (from === null || from === undefined || to === null) throw new Error(`no index for ${g} in ${BASE_MONTH} or ${latestMonth}`);
    return { group: g.slice(2), cost: (BASE_AMOUNT * to) / from };
  });

  // The year the poorest and the richest fifth differed most, by the largest monthly gap.
  const gaps = s.gaps["B"].rch_a;
  const peakI = gaps.reduce((best: number, v, i) => (v !== null && v > (gaps[best] ?? -Infinity) ? i : best), 0);
  const peak = { period: axis[peakI], value: gaps[peakI] as number };
  const peakYear = peak.period.slice(0, 4);
  const avgQ1 = s.groups["B/Q1"].avg[peakYear];
  const avgQ5 = s.groups["B/Q5"].avg[peakYear];
  if (!(peak.value > 0 && avgQ1 > avgQ5)) throw new Error(`the headline says the poorest were hit harder in ${peakYear}; the data no longer say so`);

  // Food's share of spending (division 01) in the newest year's weights, from the calculator file.
  const calc = calculator(country);
  const foodShare = (preset: string) => {
    const years = Object.keys(calc.presets[preset]).sort();
    const rows: [number, number][] = calc.presets[preset][years[years.length - 1]];
    const total = rows.reduce((a, [, w]) => a + w, 0);
    const food = rows.filter(([i]) => calc.codes[i].startsWith("01")).reduce((a, [, w]) => a + w, 0);
    return Math.round((food / total) * 100);
  };

  return { latestMonth, baskets, peak, peakYear, avgQ1, avgQ5, foodQ1: foodShare("B/Q1"), foodQ5: foodShare("B/Q5") };
}
