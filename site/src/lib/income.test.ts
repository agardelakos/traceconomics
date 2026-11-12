import { describe, expect, it } from "vitest";
import {
  equivalentSize,
  eur,
  householdType,
  pps,
  HOUSEHOLD_TYPES,
  parseAmount,
  placeIncome,
  ranges,
} from "./income";

// Eurostat's published top cut-offs for Greece, EU-SILC 2025 (incomes of 2024), euros a year per
// adult equivalent (ilc_di01, checked 2026-11-05): real figures as test inputs.
const top = { Q1: 7110, Q2: 10269, Q3: 13184, Q4: 17056 };

describe("equivalentSize", () => {
  it(
    "follows the modified OECD scale",
    {
      meta: {
        id: "VT-INCOME-001",
        given: "households of people aged 14 or over and children under 14",
        when: "their equivalent size is computed",
        then: "the first person aged 14 or over counts 1, each further one 0.5 and each child 0.3",
      },
    },
    () => {
      expect(equivalentSize(1, 0)).toBe(1);
      expect(equivalentSize(2, 0)).toBe(1.5);
      expect(equivalentSize(2, 1)).toBe(1.8);
      expect(equivalentSize(2, 2)).toBe(2.1);
      expect(equivalentSize(1, 1)).toBe(1.3);
      expect(equivalentSize(3, 0)).toBe(2);
      expect(equivalentSize(3, 1)).toBe(2.3);
    },
  );

  it(
    "refuses nobody aged 14 or over, a negative number of children, or a fractional person",
    {
      meta: {
        id: "VT-INCOME-002",
        given:
          "a household with nobody aged 14 or over, a negative number of children, or a fractional number of people",
        when: "its equivalent size is computed",
        then: "each throws an error",
      },
    },
    () => {
      expect(() => equivalentSize(0, 2)).toThrow();
      expect(() => equivalentSize(1, -1)).toThrow();
      expect(() => equivalentSize(1.5, 0)).toThrow();
    },
  );

  it(
    "gives every offered type a different size",
    {
      meta: {
        id: "VT-INCOME-003",
        given: "the household types the site offers",
        when: "their equivalent sizes are computed",
        then: "no two types have the same size",
      },
    },
    () => {
      const sizes = HOUSEHOLD_TYPES.map((h) => equivalentSize(h.older, h.children));
      expect(new Set(sizes).size).toBe(sizes.length);
    },
  );
});

describe("ranges", () => {
  it(
    "uses the published cut-offs as they are for one person",
    {
      meta: {
        id: "VT-INCOME-004",
        given: "Greece's published top cut-offs of the first four fifths",
        when: "the income ranges for one person (size 1) are built",
        then: "there are five ranges, open below the first cut-off and above the last, bounded by the cut-offs unchanged",
      },
    },
    () => {
      expect(ranges(top, 1)).toEqual([
        { from: null, to: 7110 },
        { from: 7110, to: 10269 },
        { from: 10269, to: 13184 },
        { from: 13184, to: 17056 },
        { from: 17056, to: null },
      ]);
    },
  );

  it(
    "scales them by the household's size",
    {
      meta: {
        id: "VT-INCOME-005",
        given: "Greece's published top cut-offs",
        when: "the income ranges for a household of size 2.1 are built",
        then: [
          "the first range ends at the first cut-off times 2.1, in whole euros (14931)",
          "the last range starts at the last cut-off times 2.1, in whole euros (35818)",
        ],
      },
    },
    () => {
      expect(ranges(top, 2.1)[0]).toEqual({ from: null, to: 14931 });
      expect(ranges(top, 2.1)[4]).toEqual({ from: 35818, to: null });
    },
  );

  it(
    "refuses a missing cut-off",
    {
      meta: {
        id: "VT-INCOME-006",
        given: "only three cut-offs",
        when: "the income ranges are built",
        then: "building them throws an error",
      },
    },
    () => {
      expect(() => ranges({ Q1: 1, Q2: 2, Q3: 3 }, 1)).toThrow();
    },
  );
});

describe("eur", () => {
  it(
    "writes euros the same way in every language",
    {
      meta: {
        id: "VT-INCOME-007",
        given: "amounts in euros and in PPS",
        when: "they are written",
        then: [
          "euros come first, with thousands split by a narrow space (€14 931)",
          "an amount to one decimal uses a decimal point (€130.8)",
          "an amount under a thousand has no separator (€100)",
          "-0.04 to one decimal is written €0.0, without a minus sign",
          "PPS amounts split thousands by a narrow space, with a no-break space before PPS",
        ],
      },
    },
    () => {
      expect(eur(14931)).toBe("€14\u202f931");
      expect(eur(130.8412, 1)).toBe("€130.8");
      expect(eur(100)).toBe("€100");
      expect(eur(-0.04, 1)).toBe("€0.0");
      expect(pps(8272)).toBe("8\u202f272\u00a0PPS");
    },
  );
});

describe("placeIncome", () => {
  it(
    "puts an income in its fifth, per adult equivalent",
    {
      meta: {
        id: "VT-INCOME-008",
        given: "Greece's published top cut-offs",
        when: "incomes are placed for one person and for a household of size 2.1",
        then: [
          "for one person, 5 000 is in the first fifth, 12 000 in the third and 40 000 in the fifth, each with no neighbouring fifth",
          "for size 2.1, 24 000 is in the third fifth",
        ],
      },
    },
    () => {
      expect(placeIncome(top, 1, 5000)).toEqual({ fifth: "Q1", neighbour: null });
      expect(placeIncome(top, 1, 12000)).toEqual({ fifth: "Q3", neighbour: null });
      expect(placeIncome(top, 1, 40000)).toEqual({ fifth: "Q5", neighbour: null });
      // Two adults, two children (2.1): 24 000 a year is 11 429 each, the middle fifth.
      expect(placeIncome(top, 2.1, 24000).fifth).toBe("Q3");
    },
  );

  it(
    "counts a cut-off as the top of its fifth",
    {
      meta: {
        id: "VT-INCOME-009",
        given: "the first fifth's top cut-off (7 110)",
        when: "incomes at the cut-off and one euro above are placed for one person",
        then: [
          "the income at the cut-off is in the first fifth",
          "one euro above is in the second fifth",
        ],
      },
    },
    () => {
      expect(placeIncome(top, 1, 7110).fifth).toBe("Q1");
      expect(placeIncome(top, 1, 7111).fifth).toBe("Q2");
    },
  );

  it(
    "names the fifth across a limit within 5%",
    {
      meta: {
        id: "VT-INCOME-010",
        given: "Greece's published top cut-offs",
        when: "incomes near a cut-off are placed for one person",
        then: [
          "7 000 is in the first fifth, with the second as its neighbour",
          "7 400 is in the second fifth, with the first as its neighbour",
          "17 500 is in the fifth fifth, with the fourth as its neighbour",
          "an income 6% below the first cut-off has no neighbour",
        ],
      },
    },
    () => {
      expect(placeIncome(top, 1, 7000)).toEqual({ fifth: "Q1", neighbour: "Q2" });
      expect(placeIncome(top, 1, 7400)).toEqual({ fifth: "Q2", neighbour: "Q1" });
      expect(placeIncome(top, 1, 17500)).toEqual({ fifth: "Q5", neighbour: "Q4" });
      expect(placeIncome(top, 1, 7110 * 0.94).neighbour).toBeNull();
    },
  );

  it(
    "refuses an impossible income",
    {
      meta: {
        id: "VT-INCOME-011",
        given: "a negative income and one that isn't a number",
        when: "each is placed",
        then: "each throws an error",
      },
    },
    () => {
      expect(() => placeIncome(top, 1, -1)).toThrow();
      expect(() => placeIncome(top, 1, Number.NaN)).toThrow();
    },
  );
});

describe("parseAmount", () => {
  it(
    "reads amounts typed either language's way",
    {
      meta: {
        id: "VT-INCOME-012",
        given: "amounts typed with spaces, points, commas, narrow spaces and the euro sign",
        when: "each is read",
        then: [
          "every writing of fifteen hundred reads 1500",
          "45,50 and 45.5 read 45.5",
          "1.234,56 reads 1234.56",
          "0 reads 0",
        ],
      },
    },
    () => {
      for (const s of [
        "1500",
        "1 500",
        "1.500",
        "1,500",
        "€1,500",
        "1500 €",
        `1${String.fromCharCode(0x202f)}500`,
      ])
        expect(parseAmount(s)).toBe(1500);
      expect(parseAmount("45,50")).toBe(45.5);
      expect(parseAmount("45.5")).toBe(45.5);
      expect(parseAmount("1.234,56")).toBe(1234.56);
      expect(parseAmount("0")).toBe(0);
    },
  );

  it(
    "refuses what isn't an amount",
    {
      meta: {
        id: "VT-INCOME-013",
        given: "empty and blank input, letters, a negative number and misplaced separators",
        when: "each is read as an amount",
        then: "each gives null",
      },
    },
    () => {
      for (const s of ["", " ", "abc", "-5", "1.2.3", "12.345.6", "1,2345"])
        expect(parseAmount(s)).toBeNull();
    },
  );
});

describe("householdType", () => {
  // The three arguments, named: people aged 14 or over, children under 14, and how many of those
  // aged 14 or over are dependent children (under 16, or 16 to 24 at home, neither working nor
  // looking for work).
  const type = (h: { older: number; children: number; olderDependents: number }) =>
    householdType(h.older, h.children, h.olderDependents);

  it(
    "counts adults and dependent children as Eurostat does",
    {
      meta: {
        id: "VT-INCOME-014",
        given:
          "households given as people aged 14 or over, children under 14, and dependents among those aged 14 or over",
        when: "their household type is found",
        then: [
          "one adult is A1, with children A1_DCH",
          "two adults are A2, with a child A2_DCH",
          "four adults are A_GE3, three adults with a child A_GE3_DCH",
          "three adults, one of them a dependent young adult, are A2_DCH",
        ],
      },
    },
    () => {
      expect(type({ older: 1, children: 0, olderDependents: 0 })).toBe("A1");
      expect(type({ older: 1, children: 2, olderDependents: 0 })).toBe("A1_DCH");
      expect(type({ older: 2, children: 0, olderDependents: 0 })).toBe("A2");
      expect(type({ older: 2, children: 1, olderDependents: 0 })).toBe("A2_DCH");
      expect(type({ older: 4, children: 0, olderDependents: 0 })).toBe("A_GE3");
      // A couple and a 20-year-old student at home: two adults with a dependent child, not three adults.
      expect(type({ older: 3, children: 0, olderDependents: 1 })).toBe("A2_DCH");
      expect(type({ older: 3, children: 1, olderDependents: 0 })).toBe("A_GE3_DCH");
    },
  );

  it(
    "has no type without an adult, and never counts more dependents than people",
    {
      meta: {
        id: "VT-INCOME-015",
        given:
          "households whose only adult is a dependent, with more dependents than adults, with no adults, or with a negative number of children",
        when: "their household type is found",
        then: [
          "a household whose only adult is a dependent has no type (null)",
          "one with more dependents than adults has no type (null)",
          "one with no adults throws an error",
          "one with a negative number of children throws an error",
        ],
      },
    },
    () => {
      expect(type({ older: 1, children: 0, olderDependents: 1 })).toBeNull();
      expect(type({ older: 2, children: 0, olderDependents: 5 })).toBeNull();
      expect(() => type({ older: 0, children: 1, olderDependents: 0 })).toThrow();
      expect(() => type({ older: 1, children: -1, olderDependents: 0 })).toThrow();
    },
  );
});
