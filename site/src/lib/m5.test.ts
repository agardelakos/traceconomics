import { describe, expect, it } from "vitest";
import { t } from "./i18n";
import { findings, slugOf, status, type Check } from "./m5";
import { bandLabel, periodLabel, spanLabel } from "./m5-labels";
import { m5Text, topic, topicHref } from "./topics";

const check = (over: Partial<Check>): Check => ({
  id: "gr-x", country: "gr", unit: "percent", tolerance: 1e-9,
  published: { source: "a", reference: "r", label: "p" }, rebuilt: { source: "b", reference: "r", label: "q" },
  first: "2001-01", last: "2001-12", compared: 10, agree: 10, differ: {}, differences: [], ...over,
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
});
