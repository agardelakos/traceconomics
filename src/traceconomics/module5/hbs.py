"""The household budget survey (HBS) against the office's own variables and against other surveys.

- `household_types` (a check): our six household types, built from each person's relationship
  and activity by Eurostat's written rule, against ELSTAT's own type in the same public file
  (`HB074`), year by year: each type's weighted share by both, and the share of households the
  two place alike. Two shares "agree" within `TYPE_SHARE_GAP`. A year whose ELSTAT variable
  can't be compared (`elstat_status` "unusable: …", decided when the weights run) is kept with
  its reason, never dropped.
- `spending` (a check): ELSTAT's published spending table (table 1.03, average monthly purchases
  by item) against our reading of the same survey's public use file, year by year, for all
  households and for each band where the year's bands can be rebuilt (2010-2013). Matching "to
  the cent" means within `SPENDING_TOLERANCE` (the table is rounded to the cent). Items the public
  file lacks or cuts aren't compared; they're counted apart, by year. A year whose household
  totals differ (the file's weights add up to another number of households than the table's) has
  every difference linked to the finding `SPENDING_WEIGHTS_FINDING`: the weights differ, and
  ELSTAT hasn't said why, so the cause stays "not known".
- `income_limits` (a question, "Same question, different sources"): where each income fifth
  ends, by our HBS limits and by Eurostat's EU-SILC limits for the same year's incomes. The two
  surveys measure different incomes (the HBS before some taxes and contributions SILC takes
  off), so a gap is expected and explained, not counted as disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traceconomics.module5.record import Check, Comparison, Explanation, explain

TYPES = "gr-hbs-household-types"
LIMITS = "gr-income-limits"
SPENDING = "gr-hbs-spending"
SPENDING_TOLERANCE = 0.015  # euros a month: the table's figures are rounded to the cent
SPENDING_WEIGHTS_FINDING = "survey-weights"
HOUSEHOLDS = "households"  # the archived table's row of household totals for each column
ALL_HOUSEHOLDS = "All households"  # table 1.03's name for its first column

# Percentage points of households. An assumption: wide enough for the 16-24-year-olds the two
# rules can place on either side of "dependent child" (gaps of 0.5-1.4 points in 2015-2024),
# narrow enough that a type counted differently by the office shows.
TYPE_SHARE_GAP = 1.0
# The written account of what is known about the differences without a hand-written cause (2023's
# variable, the 2009-2014 gaps): which rules were tried and what each scored. Every such difference
# links to it, so none reads "reason not known yet" without saying what was looked at.
TYPES_FINDING = "household-type-rules"


@dataclass
class Question:
    """One question answered by several sources, each with its own definition: no agreement count."""

    id: str
    country: str
    unit: str
    sources: list[dict]  # {"label", "source", "reference", "definition"}
    values: dict[str, dict[str, float]] = field(default_factory=dict)  # label -> period -> value

    def summary(self) -> dict:
        periods = sorted({p for v in self.values.values() for p in v})
        return {
            "id": self.id,
            "country": self.country,
            "unit": self.unit,
            "sources": self.sources,
            "first": periods[0] if periods else None,
            "last": periods[-1] if periods else None,
            "values": {s["label"]: {p: self.values.get(s["label"], {}).get(p) for p in periods} for s in self.sources},
        }


def household_types(
    years: dict[int, dict[str, dict[str, tuple[str | None, float | None]]]], explanations: list[Explanation]
) -> Check:
    """`years`: year -> type -> measure -> (text, number), as the store holds the archived tables."""
    check = Check(
        TYPES,
        "gr",
        "percent of households",
        TYPE_SHARE_GAP,
        published={"source": "elstat:hbs-puf", "reference": "elstat-hbs-puf", "label": "ELSTAT's type (HB074)"},
        rebuilt={"source": "oet-local:hbs_hhtypes", "reference": "elstat-hbs-puf", "label": "Eurostat's rule"},
    )
    agreement, status = {}, {}
    for year in sorted(years):
        types = years[year]
        first = types[min(types)]
        agreement[str(year)] = first["agreement"][1]
        status[str(year)] = first["elstat_status"][0] or ""
        unusable = status[str(year)].startswith("unusable")
        for group in sorted(types):
            m = types[group]
            theirs, ours = m["elstat_share_households"][1] * 100, m["share_households"][1] * 100
            period = f"{year}/{group}"
            if not unusable and abs(ours - theirs) <= TYPE_SHARE_GAP:
                check.comparisons.append(Comparison(period, theirs, ours, True))
                continue
            e = explain(TYPES, str(year), explanations)
            check.comparisons.append(
                Comparison(
                    period, theirs, ours, False, e.category if e else "not-known", e.finding if e else TYPES_FINDING
                )
            )
    check.extra = {"agreement_by_year": agreement, "elstat_status_by_year": status}
    return check


def spending(years: dict[int, dict[str, dict[str, dict[str, tuple[str | None, float | None]]]]]) -> Check:
    """`years`: year -> column (table 1.03's name) -> code -> measure -> (text, number).

    Periods are "YYYY/<column>/<code>", the column "all" for all households. An item the file has
    no column for counts as zero spending in the file (none recorded), so it shows as a difference."""
    check = Check(
        SPENDING,
        "gr",
        "EUR a month",
        SPENDING_TOLERANCE,
        published={"source": "elstat:hbs-t103", "reference": "elstat-hbs-t103", "label": "ELSTAT's table 1.03"},
        rebuilt={"source": "oet-local:hbs_spending", "reference": "elstat-hbs-puf", "label": "the public use file"},
    )
    households, excused, names = {}, {}, {}
    for year in sorted(years):
        columns = years[year]
        differ = any(c[HOUSEHOLDS]["result"][0] == "differs" for c in columns.values() if HOUSEHOLDS in c)
        total = columns.get(ALL_HOUSEHOLDS, {}).get(HOUSEHOLDS)
        if total:
            households[str(year)] = {"published": total["published"][1], "ours": total["ours"][1]}
        excused[str(year)] = 0
        for column in sorted(columns, key=lambda c: (c != ALL_HOUSEHOLDS, c)):
            key = "all" if column == ALL_HOUSEHOLDS else column
            for code in sorted(columns[column]):
                if code == HOUSEHOLDS:
                    continue
                m = columns[column][code]
                if m["result"][0] == "excused":
                    excused[str(year)] += 1
                    continue
                theirs = m["published"][1]
                ours = m.get("ours", (None, None))[1]
                ours = 0.0 if ours is None else ours
                period = f"{year}/{key}/{code}"
                if abs(ours - theirs) <= SPENDING_TOLERANCE:
                    check.comparisons.append(Comparison(period, theirs, ours, True))
                else:
                    check.comparisons.append(
                        Comparison(period, theirs, ours, False, "not-known", SPENDING_WEIGHTS_FINDING if differ else "")
                    )
                    if m.get("item", (None, None))[0]:
                        names[code] = m["item"][0]
    # ELSTAT's (English) name of each item that differs somewhere, so a page can say what it is.
    check.extra = {
        "households_by_year": households,
        "excused_by_year": excused,
        "item_names": dict(sorted(names.items())),
    }
    return check


def load_spending(store_con) -> dict:
    years: dict[int, dict] = {}
    for year, column, code, measure, text, value in _latest(
        store_con, "oet-local:hbs_spending", 'ref_period, "group", coicop, measure, value_text, value', "geo = 'GR'"
    ):
        years.setdefault(int(year), {}).setdefault(column, {}).setdefault(code, {})[measure] = (text, value)
    return years


def income_limits(ours: dict[int, dict[str, float]], silc: dict[int, dict[str, float]]) -> Question:
    """`ours`: HBS survey year -> fifth -> limit; `silc`: SILC survey year -> fifth -> limit (EUR).
    Both keyed here by the year the incomes describe: the HBS asks about the survey year, SILC
    about the year before its survey."""
    q = Question(
        LIMITS,
        "gr",
        "EUR a year per adult equivalent",
        sources=[
            {
                "label": "hbs",
                "source": "oet-local:hbs_limits",
                "reference": "elstat-hbs-puf",
                "definition": "money income after taxes, household budget survey, midpoint between the two households either side",
            },
            {
                "label": "silc",
                "source": "eurostat:ilc_di01",
                "reference": "eurostat-ilc-di01",
                "definition": "disposable income, EU-SILC, Eurostat's top cut-off",
            },
        ],
    )
    for year, limits in sorted(ours.items()):
        for g, v in sorted(limits.items()):
            q.values.setdefault("hbs", {})[f"{year}/{g}"] = v
    for year, limits in sorted(silc.items()):
        for g, v in sorted(limits.items()):
            q.values.setdefault("silc", {})[f"{year - 1}/{g}"] = v
    return q


def _latest(store_con, dataset: str, columns: str, where: str) -> list[tuple]:
    """The newest value of each key and period, withdrawn rows left out, in a fixed order."""
    if not store_con.execute("SELECT count(*) FROM observations WHERE dataset = $d", {"d": dataset}).fetchone()[0]:
        return []  # not built yet: the dataset's columns aren't in the store's view either
    return store_con.execute(
        f"""
        SELECT {columns} FROM observations WHERE dataset = $d AND {where}
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY {columns}
    """,
        {"d": dataset},
    ).fetchall()


def load_types(store_con) -> dict:
    years: dict[int, dict] = {}
    for year, group, measure, text, value in _latest(
        store_con, "oet-local:hbs_hhtypes", 'ref_period, "group", measure, value_text, value', "geo = 'GR'"
    ):
        years.setdefault(int(year), {}).setdefault(group, {})[measure] = (text, value)
    return years


def load_limits(store_con) -> tuple[dict, dict]:
    ours: dict[int, dict] = {}
    for year, group, value in _latest(
        store_con,
        "oet-local:hbs_limits",
        'ref_period, "group", value',
        "grouping = 'B' AND geo = 'GR' AND measure = 'limit'",
    ):
        ours.setdefault(int(year), {})[group] = value
    silc: dict[int, dict] = {}
    for year, quant, value in _latest(
        store_con,
        "eurostat:ilc_di01",
        "ref_period, quant_inc, value",
        "geo = 'GR' AND statinfo = 'TC' AND unit = 'EUR' "
        "AND quant_inc IN ('QU1', 'QU2', 'QU3', 'QU4') AND value IS NOT NULL",
    ):
        silc.setdefault(int(year), {})["Q" + quant[-1]] = value
    return ours, {y: v for y, v in silc.items() if len(v) == 4}
