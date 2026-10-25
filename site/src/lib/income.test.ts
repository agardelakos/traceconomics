import { describe, expect, it } from "vitest";
import cutoffs from "./income-cutoffs.json";
import { equivalentSize, eur, HOUSEHOLD_TYPES, ranges } from "./income";

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
  it("writes euros as each language does", () => {
    expect(eur("en", 14931)).toBe("€14,931");
    expect(eur("el", 14931)).toBe("14.931 €");
  });
});
