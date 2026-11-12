import { describe, expect, it } from "vitest";
import { t } from "./i18n";
import {
  chips,
  findings,
  ordered,
  roundingOnly,
  slugOf,
  status,
  termOf,
  yearRuns,
  type Check,
  type Question,
} from "./m5";
import { bandLabel, causes, checkedSpan, periodLabel, spanLabel } from "./m5-labels";
import { m5Text, topic, topicHref } from "./topics";

const check = (over: Partial<Check>): Check => ({
  id: "gr-x",
  country: "gr",
  unit: "percent",
  tolerance: 1e-9,
  published: { source: "a", reference: "r", label: "p" },
  rebuilt: { source: "b", reference: "r", label: "q" },
  first: "2001-01",
  last: "2001-12",
  compared: 10,
  agree: 10,
  by_year: {},
  differ: {},
  differences: [],
  ...over,
});

describe("consistency topic", () => {
  it(
    "says where a check stands from its differences alone",
    {
      meta: {
        id: "VT-M5-001",
        given:
          "checks where every period agrees, where every difference is rounding, where differences are rounding and a revision, where some are not known, and where all are not known",
        when: "each check's status is worked out",
        then: [
          "they read agree, agree, explained, partly and unknown",
          "a check whose only differences are rounding is consistent; rounding beside another cause is explained",
        ],
      },
    },
    () => {
      expect(status(check({}))).toBe("agree");
      expect(status(check({ agree: 8, differ: { rounding: 2 } }))).toBe("agree");
      expect(status(check({ agree: 7, differ: { rounding: 2, revision: 1 } }))).toBe("explained");
      expect(status(check({ agree: 7, differ: { rounding: 2, "not-known": 1 } }))).toBe("partly");
      expect(status(check({ agree: 7, differ: { "not-known": 3 } }))).toBe("unknown");
    },
  );

  it(
    "gives each check an address without its country, and groups findings by page",
    {
      meta: {
        id: "VT-M5-002",
        given:
          "a Greek check id, an id from another country, and a check with two differences on one finding page and one without a page",
        when: "the addresses and the findings are worked out",
        then: [
          "the Greek check's address drops the gr- prefix and the other country's id is refused",
          "the finding page lists both its periods, and the difference without a page has none",
        ],
      },
    },
    () => {
      expect(slugOf("gr-cpi-rates-own-index", "gr")).toBe("cpi-rates-own-index");
      expect(() => slugOf("cy-x", "gr")).toThrow();
      const d = (period: string, finding: string) => ({
        period,
        published: 1,
        rebuilt: 2,
        difference: 1,
        explanation: "revision" as const,
        finding,
      });
      expect(
        findings(
          check({ differences: [d("2001-06", "june"), d("2001-07", "june"), d("2001-08", "")] }),
        ),
      ).toEqual([{ slug: "june", periods: ["2001-06", "2001-07"], explanation: "revision" }]);
    },
  );

  it(
    "is live for Greece with its four pages, and its texts are Greece's",
    {
      meta: {
        id: "VT-M5-003",
        given: "the consistency topic",
        when: "its addresses and texts are asked for",
        then: [
          "it is live for gr with an overview, method, checks and same-question pages",
          "a check's page has an address under checks/",
          "its texts are found for gr and refused for another country",
        ],
      },
    },
    () => {
      const tp = topic("official-figures-consistency");
      expect(tp.status).toBe("live");
      expect(tp.countries).toEqual(["gr"]);
      expect(tp.sections).toEqual(["", "method", "checks", "same-question"]);
      expect(topicHref("en", tp.slug, "gr", "checks/cpi-rates-own-index")).toBe(
        "/en/gr/official-figures-consistency/checks/cpi-rates-own-index/",
      );
      expect(m5Text("gr", "el", "june-2001")).toBe("el/june-2001");
      expect(() => m5Text("cy", "en", "x")).toThrow();
    },
  );

  it(
    "names a period of the survey's spending table by year, column and item, in either language",
    {
      meta: {
        id: "VT-M5-004",
        given:
          "periods of the spending table for all households and for an income and a size band, and ELSTAT's English band names",
        when: "each is named in English and in Greek",
        then: [
          "all households read as the language's words for them, then the item code",
          "a band keeps ELSTAT's name in English and is translated in Greek, the euro amounts unchanged",
          "a month and a year with a group are named as before",
          "as a check's first or last period, a spending table period is its year alone, any other period as named",
        ],
      },
    },
    () => {
      expect(periodLabel("en", "2014/all/01111")).toBe(
        `2014 · ${t("en", "m5.period.all")} · 01111`,
      );
      expect(periodLabel("el", "2014/all/01111")).toBe(
        `2014 · ${t("el", "m5.period.all")} · 01111`,
      );
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
    },
  );

  it(
    "joins the years where everything agrees and puts checks with differences first",
    {
      meta: {
        id: "VT-M5-005",
        given:
          "a check's counts for 1999 to 2005 without 2004, where 2002 has a difference, and four checks: consistent, unexplained, explained, consistent",
        when: "the years are grouped and the checks ordered",
        then: [
          "1999-2001 become one row with their counts added",
          "2002 stands alone, and 2003 and 2005 aren't joined across the missing 2004",
          "the explained check comes first, then the unexplained one, then the consistent ones in their order",
        ],
      },
    },
    () => {
      const byYear = {
        "1999": { compared: 12, agree: 12 },
        "2000": { compared: 12, agree: 12 },
        "2001": { compared: 12, agree: 12 },
        "2002": { compared: 12, agree: 11 },
        "2003": { compared: 12, agree: 12 },
        "2005": { compared: 12, agree: 12 },
      };
      expect(yearRuns(byYear)).toEqual([
        { from: "1999", to: "2001", compared: 36, agree: 36 },
        { from: "2002", to: "2002", compared: 12, agree: 11 },
        { from: "2003", to: "2003", compared: 12, agree: 12 },
        { from: "2005", to: "2005", compared: 12, agree: 12 },
      ]);
      const a = check({ id: "gr-a" }),
        b = check({ id: "gr-b", agree: 9, differ: { "not-known": 1 } });
      const c = check({ id: "gr-c", agree: 9, differ: { revision: 1 } }),
        d = check({ id: "gr-d" });
      expect(ordered([a, b, c, d]).map((x) => x.id)).toEqual(["gr-c", "gr-b", "gr-a", "gr-d"]);
    },
  );

  it(
    "gives a question's card one chip per kind of source, named by who we take it from",
    {
      meta: {
        id: "VT-M5-006",
        given:
          "a question whose lines are the census, the spending survey's households and persons, Eurostat's income survey table and tax returns, and one with a source no chip names",
        when: "their chips are worked out",
        then: [
          "the chips follow the lines' order, the spending survey's two lines giving one chip",
          "Eurostat's income survey table and tax returns get their own publishers",
          "a source without a chip stops the build",
        ],
      },
    },
    () => {
      const q = (sources: string[]): Question => ({
        id: "gr-q",
        country: "gr",
        unit: "percent",
        first: null,
        last: null,
        values: {},
        sources: sources.map((s, i) => ({
          label: `l${i}`,
          source: s,
          reference: "r",
          definition: "d",
        })),
      });
      expect(
        chips(
          q([
            "eurostat:cens_21hhct_r3",
            "oet-local:hbs_rent",
            "oet-local:hbs_rent",
            "eurostat:ilc_lvho02",
            "aade:pit_stats",
          ]),
        ),
      ).toEqual(["census-eurostat", "hbs-elstat", "silc-eurostat", "tax-aade"]);
      expect(() => chips(q(["somewhere:else"]))).toThrow(/no chip for source "somewhere:else"/);
    },
  );

  it(
    "names a check's glossary term by its published source, and counts rounding-only figures",
    {
      meta: {
        id: "VT-M5-007",
        given: [
          "checks whose published side comes from ELSTAT's CPI, Eurostat's HICP, ELSTAT's household budget survey and another source",
          "a consistent check with 2 of 10 figures differing by rounding, one where all agree, and an explained check with a rounding and a revision difference",
        ],
        when: "each check's glossary term and its rounding-only count are worked out",
        then: [
          "the terms are the consumer price index, the HICP and the household budget survey; the other source has none",
          "the rounding-only counts are 2 and 0, and 0 for the explained check, whose rounding sits beside another cause",
        ],
      },
    },
    () => {
      const from = (source: string) =>
        termOf(check({ published: { source, reference: "r", label: "p" } }));
      expect(from("elstat:cpi07")).toBe("consumer-price-index");
      expect(from("eurostat:prc_hicp_midx")).toBe("hicp");
      expect(from("elstat:hbs103")).toBe("household-budget-survey");
      expect(from("ec-empl:x")).toBeUndefined();
      expect(roundingOnly(check({ agree: 8, differ: { rounding: 2 } }))).toBe(2);
      expect(roundingOnly(check({}))).toBe(0);
      expect(roundingOnly(check({ agree: 8, differ: { rounding: 1, revision: 1 } }))).toBe(0);
    },
  );

  it(
    "states the years checked and lists the causes in their fixed order",
    {
      meta: {
        id: "VT-M5-008",
        given: [
          "checks that compared no years (an empty list, and no list at all), one year, and three years given out of order",
          "a check with differences from an unknown cause, a revision and rounding, given in that order",
          "a survey period naming a group the site has no name for",
        ],
        when: "their checked span, their causes and the period's label are written in English and Greek",
        then: [
          "no years give no text, one year reads «checked 2020», three read «checked 2018–2020», and Greek uses its own words",
          "the causes read rounding, then the revision, then the unknown cause, each with its count",
          "the period reads as its year and the group's code",
        ],
      },
    },
    () => {
      expect(checkedSpan("en", check({ by_year: {} }))).toBe("");
      expect(checkedSpan("en", {} as Pick<Check, "by_year">)).toBe("");
      expect(checkedSpan("en", check({ by_year: { 2020: { compared: 1, agree: 1 } } }))).toBe(
        "checked 2020",
      );
      const three = check({
        by_year: {
          2020: { compared: 1, agree: 1 },
          2018: { compared: 1, agree: 1 },
          2019: { compared: 1, agree: 0 },
        },
      });
      expect(checkedSpan("en", three)).toBe("checked 2018–2020");
      expect(checkedSpan("el", three)).toBe(t("el", "m5.checked", { from: "2018", to: "2020" }));
      const mixed = check({ agree: 4, differ: { "not-known": 3, revision: 2, rounding: 1 } });
      expect(causes("en", mixed)).toBe(
        "1 rounding, 2 a revision not carried through, 3 reason not known yet",
      );
      expect(causes("el", mixed)).toBe(
        `1 ${t("el", "m5.cat.rounding")}, 2 ${t("el", "m5.cat.revision")}, 3 ${t("el", "m5.cat.not-known")}`,
      );
      expect(periodLabel("en", "2019/Z9")).toBe("2019 · Z9");
    },
  );
});
