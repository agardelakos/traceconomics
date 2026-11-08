import { describe, expect, it } from "vitest";
import { t } from "./i18n";
import { chips, findings, ordered, slugOf, status, yearRuns, type Check, type Question } from "./m5";
import { bandLabel, periodLabel, spanLabel } from "./m5-labels";
import { m5Text, topic, topicHref } from "./topics";

const check = (over: Partial<Check>): Check => ({
  id: "gr-x", country: "gr", unit: "percent", tolerance: 1e-9,
  published: { source: "a", reference: "r", label: "p" }, rebuilt: { source: "b", reference: "r", label: "q" },
  first: "2001-01", last: "2001-12", compared: 10, agree: 10, by_year: {}, differ: {}, differences: [], ...over,
});

describe("consistency topic", () => {
  it("says where a check stands from its differences alone", { meta: {
    id: "VT-M5-001",
    given: "checks where every period agrees, where every difference is rounding or explained, where some are not known, and where all are not known",
    when: "each check's status is worked out",
    then: [
      "they read agree, explained, partly and unknown",
      "rounding counts as a known cause",
    ],
  } }, () => {
    expect(status(check({}))).toBe("agree");
    expect(status(check({ agree: 7, differ: { rounding: 2, revision: 1 } }))).toBe("explained");
    expect(status(check({ agree: 7, differ: { rounding: 2, "not-known": 1 } }))).toBe("partly");
    expect(status(check({ agree: 7, differ: { "not-known": 3 } }))).toBe("unknown");
  });

  it("gives each check an address without its country, and groups findings by page", { meta: {
    id: "VT-M5-002",
    given: "a Greek check id, an id from another country, and a check with two differences on one finding page and one without a page",
    when: "the addresses and the findings are worked out",
    then: [
      "the Greek check's address drops the gr- prefix and the other country's id is refused",
      "the finding page lists both its periods, and the difference without a page has none",
    ],
  } }, () => {
    expect(slugOf("gr-cpi-rates-own-index", "gr")).toBe("cpi-rates-own-index");
    expect(() => slugOf("cy-x", "gr")).toThrow();
    const d = (period: string, finding: string) => ({ period, published: 1, rebuilt: 2, difference: 1, explanation: "revision" as const, finding });
    expect(findings(check({ differences: [d("2001-06", "june"), d("2001-07", "june"), d("2001-08", "")] })))
      .toEqual([{ slug: "june", periods: ["2001-06", "2001-07"], explanation: "revision" }]);
  });

  it("is live for Greece with its four pages, and its texts are Greece's", { meta: {
    id: "VT-M5-003",
    given: "the consistency topic",
    when: "its addresses and texts are asked for",
    then: [
      "it is live for gr with an overview, checks, same-question and how-we-check pages",
      "a check's page has an address under checks/",
      "its texts are found for gr and refused for another country",
    ],
  } }, () => {
    const tp = topic("official-figures-consistency");
    expect(tp.status).toBe("live");
    expect(tp.countries).toEqual(["gr"]);
    expect(tp.sections).toEqual(["", "checks", "same-question", "how-we-check"]);
    expect(topicHref("en", tp.slug, "gr", "checks/cpi-rates-own-index")).toBe("/en/gr/official-figures-consistency/checks/cpi-rates-own-index/");
    expect(m5Text("gr", "el", "june-2001")).toBe("el/june-2001");
    expect(() => m5Text("cy", "en", "x")).toThrow();
  });

  it("names a period of the survey's spending table by year, column and item, in either language", { meta: {
    id: "VT-M5-004",
    given: "periods of the spending table for all households and for an income and a size band, and ELSTAT's English band names",
    when: "each is named in English and in Greek",
    then: [
      "all households read as the language's words for them, then the item code",
      "a band keeps ELSTAT's name in English and is translated in Greek, the euro amounts unchanged",
      "a month and a year with a group are named as before",
      "as a check's first or last period, a spending table period is its year alone, any other period as named",
    ],
  } }, () => {
    expect(periodLabel("en", "2014/all/01111")).toBe(`2014 · ${t("en", "m5.period.all")} · 01111`);
    expect(periodLabel("el", "2014/all/01111")).toBe(`2014 · ${t("el", "m5.period.all")} · 01111`);
    expect(periodLabel("en", "2010/up 750 €/01111")).toBe("2010 · up 750 € · 01111");
    expect(periodLabel("el", "2010/up 750 €/01111")).toBe("2010 · έως 750 € · 01111");
    expect(bandLabel("el", "3501 and over €")).toBe("3501 και άνω €");
    expect(bandLabel("el", "751-1100 €")).toBe("751-1100 €");
    expect(bandLabel("el", "1 member")).toBe("1 μέλος");
    expect(bandLabel("el", "6 members and over")).toBe("6 μέλη και άνω");
    expect(bandLabel("en", "6 members and over")).toBe("6 members and over");
    expect(periodLabel("en", "2023")).toBe("2023");
    expect(periodLabel("en", "2022/A1")).toBe(`2022 · ${t("en", "group.hhtype/A1")}`);
    expect(spanLabel("en", "2024/all/13902")).toBe("2024");
    expect(spanLabel("en", "2022/A1")).toBe(periodLabel("en", "2022/A1"));
  });

  it("joins the years where everything agrees and puts checks with differences first", { meta: {
    id: "VT-M5-005",
    given: "a check's counts for 1999 to 2005 without 2004, where 2002 has a difference, and three checks, the middle one with differences",
    when: "the years are grouped and the checks ordered",
    then: [
      "1999-2001 become one row with their counts added",
      "2002 stands alone, and 2003 and 2005 aren't joined across the missing 2004",
      "the check with differences comes first, the consistent ones keep their order",
    ],
  } }, () => {
    const byYear = { "1999": { compared: 12, agree: 12 }, "2000": { compared: 12, agree: 12 }, "2001": { compared: 12, agree: 12 },
      "2002": { compared: 12, agree: 11 }, "2003": { compared: 12, agree: 12 }, "2005": { compared: 12, agree: 12 } };
    expect(yearRuns(byYear)).toEqual([
      { from: "1999", to: "2001", compared: 36, agree: 36 },
      { from: "2002", to: "2002", compared: 12, agree: 11 },
      { from: "2003", to: "2003", compared: 12, agree: 12 },
      { from: "2005", to: "2005", compared: 12, agree: 12 },
    ]);
    const a = check({ id: "gr-a" }), b = check({ id: "gr-b", agree: 9 }), c = check({ id: "gr-c" });
    expect(ordered([a, b, c]).map((x) => x.id)).toEqual(["gr-b", "gr-a", "gr-c"]);
  });

  it("gives a question's card one chip per kind of source, named by who we take it from", { meta: {
    id: "VT-M5-006",
    given: "a question whose lines are the census, the spending survey's households and persons, Eurostat's income survey table and tax returns, and one with a source no chip names",
    when: "their chips are worked out",
    then: [
      "the chips follow the lines' order, the spending survey's two lines giving one chip",
      "Eurostat's income survey table and tax returns get their own publishers",
      "a source without a chip stops the build",
    ],
  } }, () => {
    const q = (sources: string[]): Question => ({ id: "gr-q", country: "gr", unit: "percent", first: null, last: null, values: {},
      sources: sources.map((s, i) => ({ label: `l${i}`, source: s, reference: "r", definition: "d" })) });
    expect(chips(q(["eurostat:cens_21hhct_r3", "oet-local:hbs_rent", "oet-local:hbs_rent", "eurostat:ilc_lvho02", "aade:pit_stats"])))
      .toEqual(["census-eurostat", "hbs-elstat", "silc-eurostat", "tax-aade"]);
    expect(() => chips(q(["somewhere:else"]))).toThrow(/no chip for source "somewhere:else"/);
  });
});
