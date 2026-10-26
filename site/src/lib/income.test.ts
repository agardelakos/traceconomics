import { describe, expect, it } from "vitest";
import cutoffs from "./income-cutoffs.json";
import { equivalentSize, eur, pps, HOUSEHOLD_TYPES, parseAmount, placeIncome, ranges } from "./income";

describe("equivalentSize", () => {
  it("follows the modified OECD scale", () => {
    expect(equivalentSize(1, 0)).toBe(1);
    expect(equivalentSize(2, 0)).toBe(1.5);
    expect(equivalentSize(2, 1)).toBe(1.8);
    expect(equivalentSize(2, 2)).toBe(2.1);
    expect(equivalentSize(1, 1)).toBe(1.3);
    expect(equivalentSize(3, 0)).toBe(2);
    expect(equivalentSize(3, 1)).toBe(2.3);
  });

  it("refuses a household with nobody aged 14 or over", () => {
    expect(() => equivalentSize(0, 2)).toThrow();
    expect(() => equivalentSize(1, -1)).toThrow();
    expect(() => equivalentSize(1.5, 0)).toThrow();
  });

  it("gives every offered type a different size", () => {
    const sizes = HOUSEHOLD_TYPES.map((h) => equivalentSize(h.older, h.children));
    expect(new Set(sizes).size).toBe(sizes.length);
  });
});

describe("ranges", () => {
  const top = cutoffs.eurostat.top_cutoffs;

  it("uses the published cut-offs as they are for one person", () => {
    expect(ranges(top, 1)).toEqual([
      { from: null, to: 7110 },
      { from: 7110, to: 10269 },
      { from: 10269, to: 13184 },
      { from: 13184, to: 17056 },
      { from: 17056, to: null },
    ]);
  });

  it("scales them by the household's size", () => {
    expect(ranges(top, 2.1)[0]).toEqual({ from: null, to: 14931 });
    expect(ranges(top, 2.1)[4]).toEqual({ from: 35818, to: null });
  });

  it("refuses a missing cut-off", () => {
    expect(() => ranges({ Q1: 1, Q2: 2, Q3: 3 }, 1)).toThrow();
  });
});

describe("eur", () => {
  it("writes euros the same way in every language", () => {
    expect(eur(14931)).toBe("€14\u202f931");
    expect(eur(130.8412, 1)).toBe("€130.8");
    expect(eur(100)).toBe("€100");
    expect(eur(-0.04, 1)).toBe("€0.0");
    expect(pps(8272)).toBe("8\u202f272\u00a0PPS");
  });
});

describe("Eurostat's cut-offs", () => {
  it("come in euros and in purchasing power standards, for the same fifths", () => {
    const e = cutoffs.eurostat;
    expect(Object.keys(e.top_cutoffs_pps)).toEqual(Object.keys(e.top_cutoffs));
    // One conversion factor for the whole table: every fifth's PPS/EUR ratio agrees to rounding.
    const ratios = Object.keys(e.top_cutoffs).map((q) => (e.top_cutoffs_pps as any)[q] / (e.top_cutoffs as any)[q]);
    for (const r of ratios) expect(Math.abs(r - ratios[0])).toBeLessThan(0.002);
  });
});


describe("placeIncome", () => {
  const top = cutoffs.eurostat.top_cutoffs;   // 7110, 10269, 13184, 17056

  it("puts an income in its fifth, per adult equivalent", () => {
    expect(placeIncome(top, 1, 5000)).toEqual({ fifth: "Q1", neighbour: null });
    expect(placeIncome(top, 1, 12000)).toEqual({ fifth: "Q3", neighbour: null });
    expect(placeIncome(top, 1, 40000)).toEqual({ fifth: "Q5", neighbour: null });
    // Two adults, two children (2.1): 24 000 a year is 11 429 each, the middle fifth.
    expect(placeIncome(top, 2.1, 24000).fifth).toBe("Q3");
  });

  it("counts a cut-off as the top of its fifth", () => {
    expect(placeIncome(top, 1, 7110).fifth).toBe("Q1");
    expect(placeIncome(top, 1, 7111).fifth).toBe("Q2");
  });

  it("names the fifth across a limit within 5%", () => {
    expect(placeIncome(top, 1, 7000)).toEqual({ fifth: "Q1", neighbour: "Q2" });
    expect(placeIncome(top, 1, 7400)).toEqual({ fifth: "Q2", neighbour: "Q1" });
    expect(placeIncome(top, 1, 17500)).toEqual({ fifth: "Q5", neighbour: "Q4" });
    expect(placeIncome(top, 1, 7110 * 0.94).neighbour).toBeNull();
  });

  it("refuses an impossible income", () => {
    expect(() => placeIncome(top, 1, -1)).toThrow();
    expect(() => placeIncome(top, 1, Number.NaN)).toThrow();
  });
});

describe("parseAmount", () => {
  it("reads amounts typed either language's way", () => {
    for (const s of ["1500", "1 500", "1.500", "1,500", "€1,500", "1500 €", `1${String.fromCharCode(0x202f)}500`]) expect(parseAmount(s)).toBe(1500);
    expect(parseAmount("45,50")).toBe(45.5);
    expect(parseAmount("45.5")).toBe(45.5);
    expect(parseAmount("1.234,56")).toBe(1234.56);
    expect(parseAmount("0")).toBe(0);
  });

  it("refuses what isn't an amount", () => {
    for (const s of ["", " ", "abc", "-5", "1.2.3", "12.345.6", "1,2345"]) expect(parseAmount(s)).toBeNull();
  });
});
