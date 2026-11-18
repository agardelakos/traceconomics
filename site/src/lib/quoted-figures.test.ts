// The check that lists every figure typed into the site's text.
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  compare,
  figuresIn,
  KINDS,
  loadAllowList,
  quoted,
  siteFigures,
} from "./quoted-figures.mjs";

const SRC = path.resolve(__dirname, "..");
const pair = (en: string, el: string, id = "i18n:x") => ({ id, en, el });

describe("figures typed into the site's text", () => {
  it(
    "finds numbers with a unit in both languages' ways of writing them",
    {
      meta: {
        id: "VT-FIGS-001",
        given:
          "English and Greek sentences with percentages, points, euros, PPS, a range, a signed change and thousands grouped by a space",
        when: "their figures are read",
        then: "each figure is found once, as written, in order",
      },
    },
    () => {
      expect(
        figuresIn(
          "Rents rose 8.4% in 2025, +1.4 points; €6 680 a year, 10 300 PPS, 5–10% of spending.",
        ),
      ).toEqual(["8.4%", "+1.4 points", "€6 680", "10 300 PPS", "5–10%"]);
      expect(
        figuresIn("Τα ενοίκια αυξήθηκαν 8,4 %, −1,6 μονάδες και 1,8 ποσοστιαίες μονάδες."),
      ).toEqual(["8,4 %", "−1,6 μονάδες", "1,8 ποσοστιαίες μονάδες"]);
      expect(figuresIn("A drift of 0.0034 index points.")).toEqual(["0.0034 index points"]);
    },
  );

  it(
    "leaves out numbers without a unit and what a reader never sees",
    {
      meta: {
        id: "VT-FIGS-002",
        given:
          "a text with years, a count of months, a ratio, a placeholder filled from the data and a link whose address holds a percentage",
        when: "its figures are read",
        then: "none is found",
      },
    },
    () => {
      expect(
        figuresIn(
          "From 2011 to 2014, over 12 months, 0.69 of income; {rate} in [the table](/data?x=5%).",
        ),
      ).toEqual([]);
    },
  );

  it(
    "accepts only the figures listed for each pair, exactly as written",
    {
      meta: {
        id: "VT-FIGS-003",
        given:
          "an allow-list with one pair's figures, a pair that quotes them unchanged, a pair whose figure was edited and a pair not on the list",
        when: "the pairs are compared with the list",
        then: "the unchanged pair passes, the edited pair is reported as changed and the unlisted pair as fresh",
      },
    },
    () => {
      const allowed = [
        { id: "a", kind: "past", en: ["2.5 points"], el: ["2,5 μονάδες"] },
        { id: "b", kind: "past", en: ["8.4%"], el: ["8,4%"] },
      ];
      const found = quoted([
        pair("The gap peaked at 2.5 points.", "Η απόκλιση έφτασε 2,5 μονάδες.", "a"),
        pair("Rents rose 8.5%.", "Τα ενοίκια αυξήθηκαν 8,5%.", "b"),
        pair("Prices rose 3%.", "Οι τιμές αυξήθηκαν 3%.", "c"),
      ]);
      const r = compare(found, allowed);
      expect(r.changed.map((f: { id: string }) => f.id)).toEqual(["b"]);
      expect(r.fresh.map((f: { id: string }) => f.id)).toEqual(["c"]);
      expect(r.stale).toEqual([]);
    },
  );

  it(
    "fails an entry that no longer matches any text and one without a known kind",
    {
      meta: {
        id: "VT-FIGS-004",
        given:
          "an allow-list with an entry whose text no longer quotes a figure and an entry of an unknown kind",
        when: "today's figures are compared with the list",
        then: "the first entry is reported as stale and the second as having no known kind",
      },
    },
    () => {
      const allowed = [
        { id: "gone", kind: "past", en: ["4.9%"], el: ["4,9%"] },
        { id: "here", kind: "latest", en: ["5%"], el: ["5%"] },
      ];
      const r = compare(quoted([pair("Up 5%.", "Πάνω 5%.", "here")]), allowed);
      expect(r.stale.map((e: { id: string }) => e.id)).toEqual(["gone"]);
      expect(r.unkinded.map((e: { id: string }) => e.id)).toEqual(["here"]);
      expect(Object.keys(KINDS)).not.toContain("latest");
    },
  );

  it(
    "finds the site's own text matching its list",
    {
      meta: {
        id: "VT-FIGS-005",
        given: "the site's interface strings, content pages and src/i18n/figures-allow.json",
        when: "every figure typed into the text is compared with the list",
        then: "nothing is fresh, changed, stale or without a known kind",
      },
    },
    () => {
      const r = compare(
        siteFigures(SRC),
        loadAllowList(path.join(SRC, "i18n", "figures-allow.json")),
      );
      expect({ fresh: r.fresh, changed: r.changed, stale: r.stale, unkinded: r.unkinded }).toEqual({
        fresh: [],
        changed: [],
        stale: [],
        unkinded: [],
      });
    },
  );
});
