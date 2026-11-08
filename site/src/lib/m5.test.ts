import { describe, expect, it } from "vitest";
import { findings, slugOf, status, type Check } from "./m5";
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
});
