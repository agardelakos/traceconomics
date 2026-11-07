// The build-time readers of the published data files: the files themselves, the home page's
// figures and headline, and the bibliography. They need the files in public/data (the pipeline's,
// or made-up ones from tests/sitedata.py), so `npm run check:code` leaves this file out, as it does
// the parity test.
import { describe, expect, it } from "vitest";
import { countryFacts } from "./context";
import { calculator, latest, months, readJson, series, settings } from "./data";
import { BASE_AMOUNT, BASE_MONTH, bandLine, headline } from "./headline";
import { format, reference, references } from "./references";

describe("the data files", () => {
  it("name a default setting that exists", { meta: {
    id: "VT-DATA-001",
    given: "Greece's settings file",
    when: "its settings are read",
    then: [
      "exactly one setting is marked default",
      "that setting's slug is the file's named default",
    ],
  } }, () => {
    const s = settings("gr");
    expect(s.settings.filter((x) => x.default)).toHaveLength(1);
    expect(s.settings.find((x) => x.default)!.slug).toBe(s.default);
  });

  it("say what is missing when a file isn't there", { meta: {
    id: "VT-DATA-002",
    given: "a data path with no file behind it",
    when: "the file is read",
    then: "reading throws an error that names the `export site` command",
  } }, () => {
    expect(() => readJson("gr/m1/latest/no-such-file.json")).toThrow(/export site/);
  });

  it("give a series' month axis, one entry per value", { meta: {
    id: "VT-DATA-003",
    given: "the series file of Greece's default setting",
    when: "its month axis is built",
    then: [
      "the axis starts at the file's start month and ends at its end month",
      "it has as many months as the poorest fifth's (B/Q1) index has values",
    ],
  } }, () => {
    const file = series("gr", settings("gr").default);
    const axis = months(file);
    expect(axis[0]).toBe(file.start);
    expect(axis.at(-1)).toBe(file.end);
    expect(axis).toHaveLength(file.groups["B/Q1"].index.length);
  });

  it("find the last month with a value", { meta: {
    id: "VT-DATA-004",
    given: [
      "a start and an end month across a year boundary",
      "lists of values, some missing, with their months",
    ],
    when: "the month axis is built and the last value is looked up",
    then: [
      "the axis lists every month from start to end",
      "the last value that isn't missing is returned with its month",
      "a list with no values gives null",
    ],
  } }, () => {
    expect(months({ start: "2025-11", end: "2026-02" })).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(latest([1, 2, null], ["a", "b", "c"])).toEqual({ period: "b", value: 2 });
    expect(latest([null, null], ["a", "b"])).toBeNull();
  });
});

describe("the home page's figures", () => {
  it("carry both the published rate and ours, each with its month", { meta: {
    id: "VT-DATA-005",
    given: "Greece's facts for the home page",
    when: "the official annual rates are read",
    then: [
      "both our computed rate and the published one have a month written YYYY-MM",
      "both have a finite annual rate",
    ],
  } }, () => {
    const { official } = countryFacts("gr");
    for (const r of [official.computed, official.published]) {
      expect(r.period).toMatch(/^\d{4}-\d{2}$/);
      expect(Number.isFinite(r.annual_rate)).toBe(true);
    }
  });

  it("price the base month's shopping for the poorest and richest fifth, as the index says", { meta: {
    id: "VT-DATA-006",
    given: "Greece's headline and the series of its default setting",
    when: "the headline is built",
    then: [
      "its baskets are the poorest fifth's (Q1) and the richest fifth's (Q5), in that order",
      "each basket costs the base amount times its index in the latest month over its index in the base month (to 9 decimals)",
      "the peak year is the year of the peak month",
      "the poorest fifth's average rate is above the richest fifth's",
      "both fifths' food shares are above zero",
      "the calculator's presets include B/Q1",
    ],
  } }, () => {
    const h = headline("gr");
    const s = series("gr", settings("gr").default);
    const axis = months(s);
    expect(h.baskets.map((b) => b.group)).toEqual(["Q1", "Q5"]);
    for (const b of h.baskets) {
      const idx = s.groups[`B/${b.group}`].index;
      expect(b.cost).toBeCloseTo((BASE_AMOUNT * idx[axis.indexOf(h.latestMonth)]!) / idx[axis.indexOf(BASE_MONTH)]!, 9);
    }
    expect(h.peakYear).toBe(h.peak.period.slice(0, 4));
    expect(h.avgQ1).toBeGreaterThan(h.avgQ5);
    for (const share of [h.foodQ1, h.foodQ5]) expect(share).toBeGreaterThan(0);
    expect(Object.keys(calculator("gr").presets)).toContain("B/Q1");
  });

  it("draw the faint line inside its 330×112 box", { meta: {
    id: "VT-DATA-007",
    given: "Greece's band line for the home page",
    when: "its points are read",
    then: [
      "it has more than 12 points",
      "every x is from 0 to 330",
      "every y is from 4 to 108",
    ],
  } }, () => {
    const points = bandLine("gr").split(" ").map((p) => p.split(",").map(Number));
    expect(points.length).toBeGreaterThan(12);
    for (const [x, y] of points) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(330);
      expect(y).toBeGreaterThanOrEqual(4);
      expect(y).toBeLessThanOrEqual(108);
    }
  });
});

describe("the bibliography", () => {
  it("formats every entry, with a link where it has a DOI or address", { meta: {
    id: "VT-DATA-008",
    given: "every entry in the bibliography",
    when: "each is formatted in Greek and in English",
    then: [
      "there is at least one entry",
      "each has a title, and a lead that ends with a full stop",
      "an entry with a DOI links to its doi.org address",
      "an entry with only a web address links to that address",
      "an entry with neither has no link",
    ],
  } }, () => {
    const keys = Object.keys(references());
    expect(keys.length).toBeGreaterThan(0);
    for (const key of keys) {
      for (const lang of ["el", "en"] as const) {
        const f = format(key, lang);
        expect(f.title).toBeTruthy();
        expect(f.lead.endsWith(".")).toBe(true);
        const r = reference(key);
        if (r.doi) expect(f.link?.href).toBe(`https://doi.org/${r.doi}`);
        else if (r.url) expect(f.link?.href).toBe(r.url);
        else expect(f.link).toBeUndefined();
      }
    }
  });

  it("refuses an unknown key", { meta: {
    id: "VT-DATA-009",
    given: "a key that isn't in the bibliography",
    when: "its entry is looked up",
    then: "the lookup throws an \"unknown bibliography key\" error",
  } }, () => {
    expect(() => reference("no-such-key")).toThrow(/unknown bibliography key/);
  });
});
