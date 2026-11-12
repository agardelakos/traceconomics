import { describe, expect, it } from "vitest";
import {
  annualRate,
  chain,
  divisionShares,
  published,
  withShares,
  type CalculatorData,
} from "./calculator";
import { fixed, roundHalfEven } from "./round";

describe("roundHalfEven", () => {
  it(
    "rounds an exact halfway case to the even digit, like the pipeline",
    {
      meta: {
        id: "VT-CALCENG-001",
        given: "numbers exactly halfway between two rounded values",
        when: "they are rounded half to even",
        then: [
          "each rounds to the even last digit (100.125 to 100.12, 100.375 to 100.38, 0.25 to 0.2, -0.25 to -0.2)",
          "-0.04 to one decimal gives negative zero",
        ],
      },
    },
    () => {
      expect(roundHalfEven(100.125, 2)).toBe(100.12); // exactly representable: a true tie
      expect(roundHalfEven(100.375, 2)).toBe(100.38);
      expect(roundHalfEven(0.25, 1)).toBe(0.2);
      expect(roundHalfEven(-0.25, 1)).toBe(-0.2);
      expect(Object.is(roundHalfEven(-0.04, 1), -0)).toBe(true);
    },
  );
  it(
    "rounds everything else to the nearest",
    {
      meta: {
        id: "VT-CALCENG-002",
        given: "numbers stored just below a halfway case",
        when: "they are rounded and written with fixed decimals",
        then: [
          "2.675 rounds to 2.67 and 1.005 to 1",
          "5.049999 is written 5.0 and -0.04 is written -0.0",
        ],
      },
    },
    () => {
      expect(roundHalfEven(2.675, 2)).toBe(2.67); // 2.675 is stored as 2.67499999...
      expect(roundHalfEven(1.005, 2)).toBe(1); // 1.00499999...
      expect(fixed(5.049999, 1)).toBe("5.0");
      expect(fixed(-0.04, 1)).toBe("-0.0");
    },
  );
});

// Two years, two divisions; prices of 01 rise 1% a month in 2025, 04 stays flat.
const data: CalculatorData = {
  base_year: 2025,
  first_year: 2025,
  digits: 8,
  codes: ["011", "012", "041"],
  ratios: {
    "2025": [
      [0, Array.from({ length: 12 }, (_, m) => 1 + 0.01 * (m + 1))],
      [1, Array.from({ length: 12 }, () => 1)],
      [2, Array.from({ length: 12 }, () => 1)],
    ],
    "2026": [
      [0, [1.02, 1.04]],
      [1, [1, 1]],
      [2, [1.1, 1.1]],
    ],
  },
  presets: {
    "B/Q1": {
      "2025": [
        [0, 0.3],
        [1, 0.2],
        [2, 0.5],
      ],
      "2026": [
        [0, 0.3],
        [1, 0.2],
        [2, 0.5],
      ],
    },
  },
};

describe("chain", () => {
  it(
    "averages ratios with the weights and chains at December",
    {
      meta: {
        id: "VT-CALCENG-003",
        given: "two years of price ratios for three codes and a preset's weights",
        when: "the preset's index is chained",
        then: [
          "January 2025 is the weighted ratio rebased so 2025 averages 100 (to 10 decimals)",
          "January 2026 chains on December 2025 (to 10 decimals)",
          "there is no index for March 2026, which has no ratios",
        ],
      },
    },
    () => {
      const idx = chain(data, "B/Q1");
      const jan = 0.3 * 1.01 + 0.2 + 0.5; // weights sum to 1
      const dec = 0.3 * 1.12 + 0.2 + 0.5;
      const raw = new Map<string, number>();
      for (let m = 1; m <= 12; m++)
        raw.set(`2025-${String(m).padStart(2, "0")}`, 100 * (0.3 * (1 + 0.01 * m) + 0.7));
      const avg = [...raw.values()].reduce((a, b) => a + b, 0) / 12;
      expect(idx.get("2025-01")).toBeCloseTo(((100 * jan) / avg) * 100, 10);
      expect(idx.get("2026-01")).toBeCloseTo(
        ((100 * dec * (0.3 * 1.02 + 0.2 + 0.5 * 1.1)) / avg) * 100,
        10,
      );
      expect(idx.has("2026-03")).toBe(false); // not published yet
    },
  );

  it(
    "untouched shares give back the preset exactly",
    {
      meta: {
        id: "VT-CALCENG-004",
        given: "the preset's weights",
        when: "their division shares are taken and the index is chained with them",
        then: [
          "the shares are 0.5 for division 01 and 0.5 for division 04",
          "the index equals the preset's own, exactly",
        ],
      },
    },
    () => {
      const shares = divisionShares(
        new Map([
          ["011", 0.3],
          ["012", 0.2],
          ["041", 0.5],
        ]),
      );
      expect(shares).toEqual({ "01": 0.5, "04": 0.5 });
      expect([...chain(data, "B/Q1", shares)]).toEqual([...chain(data, "B/Q1")]);
    },
  );

  it(
    "new shares keep each year's mix inside a division",
    {
      meta: {
        id: "VT-CALCENG-005",
        given: "the preset's weights and new division shares of 0.8 and 0.2",
        when: "the weights are rescaled and the index chained with the new shares",
        then: [
          "each code keeps its part within its division (0.48, 0.32 and 0.2)",
          "the annual rate for 2026-02 differs from the preset's (at 3 decimals)",
        ],
      },
    },
    () => {
      const w = withShares(
        new Map([
          ["011", 0.3],
          ["012", 0.2],
          ["041", 0.5],
        ]),
        { "01": 0.8, "04": 0.2 },
      );
      expect(w.get("011")).toBeCloseTo(0.48, 12);
      expect(w.get("012")).toBeCloseTo(0.32, 12);
      expect(w.get("041")).toBeCloseTo(0.2, 12);
      const more = published(chain(data, "B/Q1", { "01": 0.8, "04": 0.2 }));
      const base = published(chain(data, "B/Q1"));
      expect(annualRate(more, "2026-02")!).not.toBeCloseTo(annualRate(base, "2026-02")!, 3);
    },
  );
});
