"""Consistency of official figures (module5): the checks, the explanations file and the written results."""

import csv
import json

import pytest

from traceconomics.checks import FormatError
from traceconomics.module5 import cpi
from traceconomics.module5.record import Check, Comparison, load_explanations
from traceconomics.module5.hbs import Question
from traceconomics.module5.run import write

pytestmark = pytest.mark.unit


def _index(start_year: int, values: list[float]) -> dict[str, float]:
    return {f"{start_year + i // 12}-{i % 12 + 1:02d}": v for i, v in enumerate(values)}


EXPLAINED = """
[[explanation]]
check = "gr-cpi-rates-own-index"
periods = ["2001-03"]
category = "revision"
evidence = "some-key"
finding = "march-2001"
"""


def test_own_index_counts_agreement_and_labels_each_difference():
    """PY-M5-001: rates checked against their own index: agreement, rounding, explained and unknown differences

    Given a made-up index for 2000 and 2001 and its twelve-month rates for 2001
    And one rate published rounded to one decimal, one changed and explained in the explanations, one changed and not explained
    When the rates are checked against their own index
    Then the nine other months agree, within 1e-9 points
    And the rounded month is labelled "rounding", the explained one with its category and finding page, the other "not-known"
    And no rate is compared for 2000, which has no year-ago index
    """
    index = _index(2000, [100 + i for i in range(12)] + [103 + i * 1.1 for i in range(12)])
    rate = {p: (index[p] / index[f"2000-{p[5:]}"] - 1) * 100 for p in index if p.startswith("2001")}
    rate["2001-02"] = round(rate["2001-02"], 1)
    rate["2001-03"] += 0.01
    rate["2001-04"] -= 0.02
    check = cpi.own_index(index, rate, load_explanations(EXPLAINED))
    s = check.summary()
    assert (s["compared"], s["agree"], s["first"], s["last"]) == (12, 9, "2001-01", "2001-12")
    assert s["differ"] == {"rounding": 1, "revision": 1, "not-known": 1}
    labels = {d["period"]: (d["explanation"], d["finding"]) for d in s["differences"]}
    assert labels == {"2001-02": ("rounding", ""), "2001-03": ("revision", "march-2001"), "2001-04": ("not-known", "")}


def test_rebuilt_takes_each_year_from_its_own_file():
    """PY-M5-002: our rate from table 07 uses each year's own file, with the year before's for the year-ago month

    Given two made-up table 07 files, for 2020 and 2021, whose overall index levels for 2020 differ slightly
    And published rates for 2021 equal to the 2021 file's levels over the 2020 file's
    When our rates are checked against the published ones
    Then all twelve months of 2021 agree, so the 2020 file's own levels were used for the year-ago months
    """
    y20 = _index(2020, [100 + i * 0.5 for i in range(12)])
    y21 = _index(2021, [104 + i * 0.4 for i in range(12)])
    blocks = {2020: {"TOTAL": y20}, 2021: {"TOTAL": {**{p: v * 1.001 for p, v in y20.items()}, **y21}}}
    rate = {p: (y21[p] / y20[f"2020-{p[5:]}"] - 1) * 100 for p in y21}
    s = cpi.rebuilt(blocks, rate, []).summary()
    assert (s["compared"], s["agree"]) == (12, 12)


def test_explanations_file_refuses_what_it_cannot_vouch_for():
    """PY-M5-003: the explanations file refuses entries without evidence, without periods, or with a category the code decides

    Given explanation entries with no evidence key, with no periods, with category "rounding" and with an unknown category
    When each is loaded
    Then each is refused with a FormatError
    And the shipped explanations file loads, with June 2001 in table 05 explained as a revision
    """
    base = 'check = "c"\nperiods = ["2001-01"]\ncategory = "revision"\nevidence = "k"\n'
    for bad in [
        base.replace('evidence = "k"\n', ""),
        base.replace('["2001-01"]', "[]"),
        base.replace('"revision"', '"rounding"'),
        base.replace('"revision"', '"error"'),
    ]:
        with pytest.raises(FormatError):
            load_explanations("[[explanation]]\n" + bad)
    shipped = load_explanations()
    june = [e for e in shipped if e.check == cpi.OWN_INDEX and "2001-06" in e.periods]
    assert len(june) == 1 and june[0].category == "revision" and june[0].finding == "june-2001"


def test_results_are_written_in_a_fixed_order(tmp_path):
    """PY-M5-004: the results files are the same bytes whatever order the comparisons arrive in

    Given one check whose comparisons arrive out of order, one of them a difference
    When the results are written twice, once with the comparisons reversed
    Then both runs write identical checks.json and CSV files, rows in period order
    And checks.json gives the count compared, the count agreeing and the difference with its explanation
    And it gives each year's count compared and agreeing
    """
    rows = [Comparison("2001-02", 1.0, 1.0, True), Comparison("2001-01", 2.0, 2.5, False, "not-known")]

    def make(order):
        c = Check("gr-x", "gr", "percent", 1e-9, {"source": "a"}, {"source": "b"})
        c.comparisons = list(order)
        return c

    a, b = tmp_path / "a", tmp_path / "b"
    write([make(rows)], a)
    write([make(reversed(rows))], b)
    for name in ("checks.json", "gr-x.csv"):
        assert (a / "gr" / "m5" / name).read_bytes() == (b / "gr" / "m5" / name).read_bytes()
    doc = json.loads((a / "gr" / "m5" / "checks.json").read_text(encoding="utf-8"))
    s = doc["checks"][0]
    assert (s["compared"], s["agree"], s["differ"]) == (2, 1, {"not-known": 1})
    assert s["differences"][0]["difference"] == 0.5
    assert s["by_year"] == {"2001": {"compared": 2, "agree": 1}}
    lines = list(csv.reader((a / "gr" / "m5" / "gr-x.csv").open(encoding="utf-8")))
    assert [r[0] for r in lines[1:]] == ["2001-01", "2001-02"]


def test_rebuild_months_off_by_more_than_rounding_are_findings():
    """PY-M5-005: a rebuilt rate off by more than 0.1 points is a finding, not rounding

    Given a comparison of three months: equal once rounded, 0.1 apart once rounded, and 0.3 apart
    When it is turned into a published check, with no explanation written
    Then the first agrees, the second is "rounding" and the third "not-known"
    """
    from traceconomics.module5.rebuilds import from_validation
    from traceconomics.validate.compare import Comparison as Validation

    v = Validation(name="x", rows=[("2020-01", 1.04, 1.01), ("2020-02", 1.06, 0.96), ("2020-03", 1.3, 1.0)])
    s = from_validation("gr-x", v, {"source": "a"}, {"source": "b"}, []).summary()
    assert (s["compared"], s["agree"]) == (3, 1)
    assert [(d["period"], d["explanation"]) for d in s["differences"]] == [
        ("2020-02", "rounding"),
        ("2020-03", "not-known"),
    ]


def _types(year, rows, agreement, status="compared"):
    return {
        year: {
            g: {
                "share_households": (None, ours),
                "elstat_share_households": (None, theirs),
                "agreement": (None, agreement),
                "elstat_status": (status, None),
            }
            for g, ours, theirs in rows
        }
    }


def test_household_types_compare_shares_and_keep_unusable_years():
    """PY-M5-006: household types: shares within one point agree, an unusable ELSTAT year is kept and never agrees

    Given 2022 with two types, one 0.5 points from ELSTAT's share and one 2 points off, 98% of households alike
    And 2023, whose ELSTAT type is marked unusable, with shares that happen to match
    When the household types are checked
    Then in 2022 the close type agrees and the other is "not-known"
    And both 2023 types are differences, "not-known", since ELSTAT's variable can't be compared
    And the agreement and status of each year are kept with the check
    And every difference without a written cause links to the household-type finding
    """
    from traceconomics.module5.hbs import TYPES_FINDING, household_types

    years = {
        **_types(2022, [("A1", 0.200, 0.205), ("A2", 0.300, 0.280)], 0.98),
        **_types(2023, [("A1", 0.25, 0.25), ("A2", 0.30, 0.30)], 0.27, "unusable: broken"),
    }
    s = household_types(years, []).summary()
    assert (s["compared"], s["agree"]) == (4, 1)
    assert [d["period"] for d in s["differences"]] == ["2022/A2", "2023/A1", "2023/A2"]
    assert s["extra"]["agreement_by_year"] == {"2022": 0.98, "2023": 0.27}
    assert s["extra"]["elstat_status_by_year"]["2023"].startswith("unusable")
    assert {d["finding"] for d in s["differences"]} == {TYPES_FINDING}


def test_income_limits_line_up_by_the_year_the_incomes_describe(tmp_path):
    """PY-M5-007: income limits: each survey's limits keyed by the year its incomes describe

    Given our HBS limits for survey 2024 and Eurostat's EU-SILC limits for surveys 2024 and 2025
    When the question is built and written
    Then the HBS 2024 limits and SILC 2025's sit under income year 2024, SILC 2024's under 2023
    And the CSV has one row per period and source, and checks.json lists the question with both sources' definitions
    """
    from traceconomics.module5.hbs import income_limits

    q = income_limits(
        {2024: {"Q1": 8000.0, "Q2": 10800.0}}, {2024: {"Q1": 6653.0, "Q2": 9513.0}, 2025: {"Q1": 7110.0, "Q2": 10269.0}}
    )
    s = q.summary()
    assert s["values"]["hbs"]["2024/Q1"] == 8000.0 and s["values"]["silc"]["2024/Q1"] == 7110.0
    assert s["values"]["silc"]["2023/Q1"] == 6653.0 and s["values"]["hbs"]["2023/Q1"] is None
    write([], tmp_path, [q])
    rows = list(csv.reader((tmp_path / "gr" / "m5" / "gr-income-limits.csv").open(encoding="utf-8")))
    assert rows[0] == ["period", "source", "value"] and len(rows) == 1 + 2 + 4
    doc = json.loads((tmp_path / "gr" / "m5" / "checks.json").read_text(encoding="utf-8"))
    assert [x["label"] for x in doc["questions"][0]["sources"]] == ["hbs", "silc"]
    assert all(x["definition"] for x in doc["questions"][0]["sources"])


DIMS = (
    "geo",
    "hhcomp",
    "unit",
    "tenure",
    "rskpovth",
    "measure",
    "coicop",
    "direct",
    "na_item",
    "sector",
    "age",
    "sex",
    "regis_es",
    "stk_flow",
    "coicop18",
    "grouping",
    "spending",
    "imputed_rent",
)


def _store(rows):
    """An in-memory stand-in for the store's observations view: (dataset, period, value, {dimension: code})."""
    import duckdb

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE observations (dataset VARCHAR, key VARCHAR, ref_period VARCHAR, value DOUBLE, "
        "value_text VARCHAR, published_at VARCHAR, retrieved_at VARCHAR, status VARCHAR, "
        + ", ".join(f"{d} VARCHAR" for d in DIMS)
        + ")"
    )
    for ds, period, value, dims in rows:
        key = ",".join(f"{k}={dims[k]}" for k in sorted(dims))
        con.execute(
            f"INSERT INTO observations VALUES (?, ?, ?, ?, ?, '2026-11-08', '2026-11-08', 'new', "
            + ", ".join("?" * len(DIMS))
            + ")",
            [ds, key, period, value, repr(value), *[dims.get(d) for d in DIMS]],
        )
    return con


def test_renters_line_up_households_and_persons_by_source():
    """PY-M5-008: renters: each source's share of households or persons renting, by year

    Given a made-up store with census 2021 (1,062,653 tenant households of 4,332,446), the SILC and HBS tenure tables for 2021, and Eurostat's SILC share of persons at market rent
    When the renters question is built
    Then the census line reads 24.5% for 2021, the SILC households line 24.0% and the HBS households line 16.8%
    And the persons lines are Eurostat's 20.3% and the HBS's 15.0%
    And each line carries its definition and reference key
    """
    from traceconomics.module5 import questions

    g = {"geo": "GR"}
    rows = [
        ("eurostat:cens_21hhct_r3", "2021", 1062653, {**g, "hhcomp": "TOTAL", "unit": "NR", "tenure": "RENT"}),
        ("eurostat:cens_21hhct_r3", "2021", 4332446, {**g, "hhcomp": "TOTAL", "unit": "NR", "tenure": "TOTAL"}),
        (
            "eurostat:ilc_lvho02",
            "2021",
            20.3,
            {**g, "hhcomp": "TOTAL", "rskpovth": "TOTAL", "unit": "PC", "tenure": "RENT_MKT"},
        ),
    ]
    for ds, renters, total in (("oet-local:silc_tenure", 24.0, 100.0), ("oet-local:hbs_rent", 16.8, 100.0)):
        rows += [
            (ds, "2021", renters, {**g, "tenure": "renter", "measure": "households_weighted"}),
            (ds, "2021", total, {**g, "tenure": "all", "measure": "households_weighted"}),
        ]
    rows += [
        ("oet-local:hbs_rent", "2021", 15.0, {**g, "tenure": "renter", "measure": "people_weighted"}),
        ("oet-local:hbs_rent", "2021", 100.0, {**g, "tenure": "all", "measure": "people_weighted"}),
    ]
    s = questions.renters(_store(rows)).summary()
    v = s["values"]
    assert (
        round(v["census"]["2021"], 1) == 24.5 and v["silc"]["2021"] == 24.0 and v["hbs"]["2021"] == pytest.approx(16.8)
    )
    assert v["silc_persons"]["2021"] == 20.3 and v["hbs_persons"]["2021"] == 15.0
    assert all(x["definition"] and x["reference"] for x in s["sources"])


def test_a_question_needs_two_sources_and_keeps_aades_text():
    """PY-M5-009: a question with one source is left out; AADE's figures go in unchanged

    Given a made-up store with only the labour force survey's unemployed for 2024
    And another with the national accounts' disposable income (140,001 million euros) and AADE's declared income (91,674,362,821.89 euros) for 2022
    When the unemployment question is built from the first and the household income question from the second
    Then the unemployment question is left out, since one source alone is not a comparison
    And the national accounts line reads 140,001,000,000 euros and AADE's exactly 91,674,362,821.89
    """
    from traceconomics.module5 import questions

    lfs = [("eurostat:une_rt_a", "2024", 450.0, {"geo": "GR", "age": "Y15-74", "unit": "THS_PER", "sex": "T"})]
    assert questions.unemployment(_store(lfs)) is None
    rows = [
        (
            "eurostat:nasa_10_nf_tr",
            "2022",
            140001.0,
            {"geo": "GR", "unit": "CP_MEUR", "direct": "RECV", "na_item": "B6G", "sector": "S14_S15"},
        ),
        ("aade:pit_stats", "2022", 91674362821.89, {"geo": "GR", "measure": "declared_income", "unit": "EUR"}),
    ]
    v = questions.household_income(_store(rows)).summary()["values"]
    assert v["national_accounts"]["2022"] == 140001e6 and v["aade"]["2022"] == 91674362821.89


def test_rent_weight_puts_every_source_in_percent_of_spending():
    """PY-M5-010: rent's weight: the indices' per mille and the national accounts' share become percent

    Given a made-up store with the CPI's rent weight 36.3 per mille and the HICP's 31.1 for 2024, the national accounts' actual rentals (8,116.4) and all consumption (169,881.8) for 2023, and the HBS's rent share of purchases 0.0423 for 2024
    When the rent-weight question is built
    Then the CPI reads 3.63%, the HICP 3.11%, the national accounts 4.78% and the HBS 4.23%
    """
    from traceconomics.module5 import questions

    rows = [
        ("elstat:cpi07", "2024", 36.3, {"unit": "PM", "coicop18": "041"}),
        ("eurostat:prc_hicp_iw", "2024", 31.1, {"geo": "GR", "coicop18": "041"}),
        ("eurostat:nama_10_co3_p3", "2023", 8116.4, {"geo": "GR", "unit": "CP_MEUR", "coicop": "CP041"}),
        ("eurostat:nama_10_co3_p3", "2023", 169881.8, {"geo": "GR", "unit": "CP_MEUR", "coicop": "TOTAL"}),
        (
            "oet-local:hbs_weights",
            "2024",
            0.0423,
            {
                "geo": "GR",
                "grouping": "all",
                "spending": "purchases",
                "imputed_rent": "excluded",
                "coicop18": "041",
                "measure": "share",
            },
        ),
    ]
    v = questions.rent_weight(_store(rows)).summary()["values"]
    assert round(v["cpi"]["2024"], 2) == 3.63 and round(v["hicp"]["2024"], 2) == 3.11
    assert round(v["national_accounts"]["2023"], 2) == 4.78 and round(v["hbs"]["2024"], 2) == 4.23


def test_rent_change_indexes_average_rents_to_2015():
    """PY-M5-011: rent change: each survey's average rent per renting household, as an index with 2015 = 100

    Given a made-up store without table 07, and the HBS and SILC rent tables for 2015, 2020 and 2021 (rent paid and renting households), and a third survey table without 2015
    When the rent-change question is built
    Then the CPI line is left out, since table 07 isn't in the store
    And the HBS line reads 100 in 2015 and 105 in 2021 (average rent 3,600 to 3,780 a year), the SILC line 100 and 110 (3,000 to 3,300)
    And a line without a 2015 value gives no index
    """
    from traceconomics.module5 import questions

    rows = []
    for ds, (r15, r20, r21) in (
        ("oet-local:hbs_rent", (3600.0, 3700.0, 3780.0)),
        ("oet-local:silc_tenure", (3000.0, 3100.0, 3300.0)),
    ):
        for year, rent in (("2015", r15), ("2020", r20), ("2021", r21)):
            rows += [
                (ds, year, rent * 100, {"geo": "GR", "tenure": "all", "measure": "rent_paid_eur"}),
                (ds, year, 100.0, {"geo": "GR", "tenure": "renter", "measure": "households_weighted"}),
            ]
    con = _store(rows)
    con.execute("ALTER TABLE observations ADD COLUMN archive_dataset VARCHAR")
    q = questions.rent_change(con)
    s = q.summary()
    assert q.unit == "index" and [x["label"] for x in s["sources"]] == ["hbs", "silc"]
    v = s["values"]
    assert round(v["hbs"]["2015"], 6) == 100.0 and round(v["hbs"]["2021"], 6) == 105.0
    assert round(v["silc"]["2015"], 6) == 100.0 and round(v["silc"]["2021"], 6) == 110.0
    assert questions._index({"2020": 3000.0, "2021": 3300.0}) == {}


def test_attribution_names_every_publisher_and_dataset_the_questions_use(tmp_path):
    """PY-M5-012: the files' attribution names every publisher and every Eurostat dataset the questions draw on

    Given the sources every question names (publisher prefix and dataset), and a results file written
    When its attribution is read
    Then it names ELSTAT, Eurostat, AADE and the European Commission's DG EMPL
    And it says AADE's figures are shown as published
    And every Eurostat and DG EMPL dataset a question names is listed in it
    """
    import re
    from pathlib import Path
    from traceconomics.module5 import questions

    write(
        [],
        tmp_path,
        [
            Question(
                "gr-x", "gr", "EUR", [{"label": "a", "source": "aade:pit_stats", "reference": "r", "definition": "d"}]
            )
        ],
    )
    text = json.loads((tmp_path / "gr" / "m5" / "checks.json").read_text(encoding="utf-8"))["attribution"]
    for name in ("ELSTAT", "Eurostat", "AADE", "European Commission", "DG EMPL"):
        assert name in text, name
    assert "shown as published" in text
    used = set(
        re.findall(r'"source": "(?:eurostat|ec-empl):(\w+)"', Path(questions.__file__).read_text(encoding="utf-8"))
    )
    assert used and not {d for d in used if d not in text}


def test_spending_check_counts_figures_to_the_cent_and_links_years_with_other_weights():
    """PY-M5-013: the spending check: figures to the cent agree, excused items are counted apart, and a year weighted differently links its differences to the finding

    Given a made-up store with the spending tables of 2013 (households match; one item to the cent, one excused, an income band to the cent) and 2014 (households differ; one item to the cent, one 5 cents off, one the file has no column for)
    When the spending check is built from the store
    Then 5 figures are compared and 3 agree, the excused item left out and counted for 2013
    And 2014's two differences are "not-known" and link to the survey-weights finding, the missing column read as zero
    And the household totals are kept by year, and periods name the year, the column ("all" for all households) and the item
    And the name of each item that differs is kept where the table gives one
    """
    import duckdb
    from traceconomics.module5 import hbs

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE observations (dataset VARCHAR, key VARCHAR, ref_period VARCHAR, value DOUBLE, value_text VARCHAR, "
        'published_at VARCHAR, retrieved_at VARCHAR, status VARCHAR, geo VARCHAR, "group" VARCHAR, coicop VARCHAR, '
        "measure VARCHAR)"
    )

    def add(year, column, code, published, ours, result):
        for m, v in (("published", published), ("ours", ours), ("result", result)):
            if v is None:
                continue
            con.execute(
                "INSERT INTO observations VALUES ('oet-local:hbs_spending', ?, ?, ?, ?, '2026-11-08', '2026-11-08', "
                "'new', 'GR', ?, ?, ?)",
                [f"{column}|{code}|{m}", year, v if m != "result" else None, str(v), column, code, m],
            )

    all_ = hbs.ALL_HOUSEHOLDS
    add("2013", all_, "households", 4178116.0, 4178116.0, "matched")
    add("2013", all_, "01111", 12.34, 12.3412, "matched")
    add("2013", all_, "07242", 17.5, 1.02, "excused")
    add("2013", "up 750 €", "households", 600000.0, 600000.0, "matched")
    add("2013", "up 750 €", "01111", 7.1, 7.1, "matched")
    add("2014", all_, "households", 4152372.0, 4136073.0, "differs")
    add("2014", all_, "01111", 12.0, 12.0, "matched")
    add("2014", all_, "01112", 3.2, 3.25, "differs")
    con.execute(
        "INSERT INTO observations VALUES ('oet-local:hbs_spending', 'i', '2014', NULL, 'Bread', '2026-11-08', "
        "'2026-11-08', 'new', 'GR', ?, '01112', 'item')",
        [all_],
    )
    add("2014", all_, "03111", 0.09, None, "differs")
    c = hbs.spending(hbs.load_spending(con))
    s = c.summary()
    assert (s["compared"], s["agree"], s["differ"]) == (5, 3, {"not-known": 2})
    assert [d["period"] for d in s["differences"]] == ["2014/all/01112", "2014/all/03111"]
    assert {d["finding"] for d in s["differences"]} == {hbs.SPENDING_WEIGHTS_FINDING}
    assert s["differences"][1]["rebuilt"] == 0.0
    assert "2013/up 750 €/01111" in [x.period for x in c.comparisons]
    assert s["extra"]["excused_by_year"] == {"2013": 1, "2014": 0}
    assert s["extra"]["households_by_year"]["2014"] == {"published": 4152372.0, "ours": 4136073.0}
    assert s["extra"]["item_names"] == {"01112": "Bread"}


def _validation(rows, name="finest detail"):
    """A stand-in for the engine's validation result: its name and (period, ours, theirs) rows."""
    from types import SimpleNamespace

    return SimpleNamespace(name=name, rows=rows)


def test_cpi_rebuild_labels_each_month_from_the_validation(monkeypatch):
    """PY-M5-014: the CPI rebuilt from table 07: each month the validation compared, labelled

    Given the validation of the CPI rebuilt from table 07 with three months: equal at one decimal, 0.1 apart, and 0.3 apart
    When the check is built
    Then it is the items check, both sides citing table 07
    And the months read: agree, rounding, and a difference whose cause isn't known
    """
    from traceconomics.module5 import rebuilds
    from traceconomics.validate import v1_cpi

    rows = [("2015-01", 1.02, 1.04), ("2015-02", 1.06, 1.16), ("2015-03", 2.0, 2.3)]
    monkeypatch.setattr(v1_cpi, "run_archive", lambda archive: (_validation(rows), None, 0, {}))
    c = rebuilds.cpi(None, [])
    assert c.id == rebuilds.CPI and c.published["reference"] == c.rebuilt["reference"] == "elstat-cpi-items"
    assert [(x.period, x.agree, x.explanation) for x in c.comparisons] == [
        ("2015-01", True, ""),
        ("2015-02", False, "rounding"),
        ("2015-03", False, "not-known"),
    ]


def test_hicp_rebuild_uses_the_finest_detail_and_is_left_out_without_its_files(monkeypatch, tmp_path):
    """PY-M5-015: the HICP rebuilt: only the finest detail is published, and nothing without both files

    Given an archive with Eurostat's item indices but not their weights
    And then one with both, whose validation gives a coarse level and the finest detail
    When the HICP check is built each time
    Then without the weights there is no check
    And with both the check holds only the finest detail's months
    And a validation without the finest detail gives no check either
    """
    from types import SimpleNamespace
    from traceconomics.module5 import rebuilds
    from traceconomics.validate import v1

    held = {"prc_hicp_minr": {"path": "minr.tsv"}}
    archive = SimpleNamespace(latest=lambda source, name: held.get(name))
    assert rebuilds.hicp(archive, tmp_path, None, []) is None
    held["prc_hicp_iw"] = {"path": "iw.tsv"}
    monkeypatch.setattr(v1, "load", lambda duck, minr, iw, geo: ({}, {}, {"2024-12": 2.9}, {}))
    found = [
        _validation([("2024-12", 2.0, 2.0)], "two digits"),
        _validation([("2024-11", 3.0, 3.0), ("2024-12", 2.9, 2.9)]),
    ]
    monkeypatch.setattr(v1, "run", lambda *a, **k: found)
    c = rebuilds.hicp(archive, tmp_path, None, [])
    assert c.id == rebuilds.HICP and [x.period for x in c.comparisons] == ["2024-11", "2024-12"]
    monkeypatch.setattr(v1, "run", lambda *a, **k: found[:1])
    assert rebuilds.hicp(archive, tmp_path, None, []) is None


def test_all_checks_in_order_without_missing_parts_and_never_two_with_one_id(monkeypatch):
    """PY-M5-016: every check is gathered in a fixed order, a missing part is left out, and a repeated id stops the run

    Given the CPI checks, the CPI rebuild, no HICP rebuild, household types and the spending table, each made up
    When all checks are gathered
    Then they come in that order, without the HICP
    And two checks sharing an id stop the run with a FormatError naming the ids
    """
    from traceconomics.module5 import cpi as m5cpi, hbs, rebuilds, run

    made = lambda cid: Check(cid, "gr", "percent", 0.0, {}, {})
    monkeypatch.setattr(m5cpi, "checks", lambda con, ex: [made("gr-a"), made("gr-b")])
    monkeypatch.setattr(rebuilds, "cpi", lambda archive, ex: made("gr-c"))
    monkeypatch.setattr(rebuilds, "hicp", lambda archive, d, duck, ex: None)
    monkeypatch.setattr(hbs, "load_types", lambda con: {2024: {}})
    monkeypatch.setattr(hbs, "household_types", lambda years, ex: made("gr-d"))
    monkeypatch.setattr(hbs, "load_spending", lambda con: {2024: {}})
    monkeypatch.setattr(hbs, "spending", lambda years: made("gr-e"))
    assert [c.id for c in run.all_checks(None, None, ".", None)] == ["gr-a", "gr-b", "gr-c", "gr-d", "gr-e"]
    monkeypatch.setattr(rebuilds, "cpi", lambda archive, ex: made("gr-a"))
    with pytest.raises(FormatError, match="check ids repeat"):
        run.all_checks(None, None, ".", None)


def _cpi05_store(rows):
    """A stand-in store holding table 05: (unit, period, value, status, published_at)."""
    import duckdb

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE observations (dataset VARCHAR, key VARCHAR, freq VARCHAR, unit VARCHAR, ref_period VARCHAR, "
        "value DOUBLE, status VARCHAR, published_at VARCHAR, retrieved_at VARCHAR)"
    )
    for unit, period, value, status, published in rows:
        con.execute(
            "INSERT INTO observations VALUES ('elstat:cpi05', ?, 'M', ?, ?, ?, ?, ?, ?)",
            [f"unit={unit}", unit, period, value, status, published, published],
        )
    return con


def test_table05_reads_the_newest_rows_rates_in_percent():
    """PY-M5-017: table 05 is read from the store: the newest version of each month, rates in percent, withdrawn rows left out

    Given a store with table 05's index and its yearly rate as a fraction, one month published twice, and one month withdrawn
    When table 05 is read
    Then the index keeps each month's newest value
    And the rate is in percent, from the newest version
    And the withdrawn month is in neither
    """
    con = _cpi05_store(
        [
            ("I20", "2001-06", 80.0, "new", "2026-01"),
            ("I20", "2001-06", 80.5, "changed", "2026-02"),
            ("RCH_A_FR", "2001-06", 0.039332, "new", "2026-01"),
            ("RCH_A_FR", "2001-06", 0.039239, "changed", "2026-02"),
            ("I20", "2001-07", 81.0, "new", "2026-01"),
            ("I20", "2001-07", 81.0, "withdrawn", "2026-02"),
        ]
    )
    index, rate = cpi.table05(con)
    assert index == {"2001-06": 80.5}
    assert rate == {"2001-06": pytest.approx(3.9239)}


def test_household_types_are_read_by_year_type_and_measure():
    """PY-M5-018: the household types table is read from the store by year, type and measure

    Given a store with two types' shares for 2023, ELSTAT's status as text, and a row for another country
    When the household types are loaded
    Then they are grouped by year, then type, then measure, each as its text and number
    And the other country's row is left out
    """
    import duckdb
    from traceconomics.module5 import hbs

    con = duckdb.connect()
    con.execute(
        'CREATE TABLE observations (dataset VARCHAR, key VARCHAR, geo VARCHAR, "group" VARCHAR, measure VARCHAR, '
        "ref_period VARCHAR, value DOUBLE, value_text VARCHAR, status VARCHAR, published_at VARCHAR, retrieved_at VARCHAR)"
    )
    for geo, group, measure, text, value in [
        ("GR", "A1", "share_households", "0.25", 0.25),
        ("GR", "A2", "share_households", "0.3", 0.3),
        ("GR", "A1", "elstat_status", "unusable: broken", None),
        ("CY", "A1", "share_households", "0.2", 0.2),
    ]:
        con.execute(
            "INSERT INTO observations VALUES ('oet-local:hbs_hhtypes', ?, ?, ?, ?, '2023', ?, ?, 'new', 'p', 'r')",
            [f"{geo}|{group}|{measure}", geo, group, measure, value, text],
        )
    assert hbs.load_types(con) == {
        2023: {
            "A1": {"share_households": ("0.25", 0.25), "elstat_status": ("unusable: broken", None)},
            "A2": {"share_households": ("0.3", 0.3)},
        }
    }
