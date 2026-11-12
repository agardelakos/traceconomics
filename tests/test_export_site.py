"""The website's data files, on made-up series: the calculator file rebuilds the series exactly,
and the per-setting files carry what the outputs hold."""

import json

import duckdb
import pytest

from traceconomics.checks import FormatError
from traceconomics.export import calculator, site
from traceconomics.module1 import availability, combinations, index, output
from traceconomics.module1.weights_used import Basket

pytestmark = pytest.mark.integration


def blocks():
    b = {}
    for y in range(2008, 2027):
        last = 9 if y == 2026 else 12
        b[y] = {
            c: {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * k + (y % 3) * 0.17 * m for m in range(1, last + 1)}}
            for c, k in (("011", 0.61), ("012", 0.23), ("041", 0.31), ("07", 0.83))
        }
    return b


def baskets(groups):
    out = {}
    for h in range(2008, 2025):
        for n, (g, q) in enumerate(groups):
            shares = {
                "01": 0.4,
                "011": 0.3 + 0.01 * n,
                "012": 0.1 - 0.01 * n,
                "04": 0.25,
                "041": 0.25,
                "07": 0.35 - 0.001 * h % 7,
            }
            out[(h, g, q)] = Basket(shares, dict.fromkeys(shares, "normal"))
    return out


def presets():
    b, k = blocks(), baskets(calculator.PRESETS)
    return [index.build(None, g, q, blocks=b, baskets=k) for g, q in calculator.PRESETS], b


def test_calculator_file_rebuilds_every_preset_exactly():
    """PY-SITEEXP-001: the calculator file rebuilds every preset exactly

    Given made-up price blocks for 2008 to 2026-09 and baskets for every calculator preset
    And the index series built for each preset
    When the calculator file is built from 2019 with 12 digits
    Then it starts in 2019 and holds one entry per preset
    And the B/Q1 weights and the price ratios in the file rebuild that series' published values to 2 decimals for every month from 2019-01
    And the 2026 ratios have at most 9 months: months not out yet are left off
    """
    series, b = presets()
    data = calculator.build(series, b, first_year=2019, digits=12)
    assert data["first_year"] == 2019 and set(data["presets"]) == {f"{g}/{q}" for g, q in calculator.PRESETS}
    codes = data["codes"]
    w = {y: {codes[i]: v for i, v in rows} for y, rows in data["presets"]["B/Q1"].items()}
    r = {y: {codes[i]: v for i, v in rows} for y, rows in data["ratios"].items()}
    rebuilt = calculator.rebuild(w, r, 2019)
    s = next(x for x in series if (x.grouping, x.group) == ("B", "Q1"))
    assert all(round(v, 2) == s.published[p] for p, v in rebuilt.items() if p >= "2019-01")
    assert max(len(v) for _, v in data["ratios"]["2026"]) == 9  # months not out yet are left off


def test_calculator_weights_are_summed_by_the_index_that_prices_them():
    """PY-SITEEXP-002: calculator weights are summed under the index that prices them

    Given a preset series whose 2020 weights price class 012 with the index of 011
    When the preset's 2020 weights are taken for the calculator
    Then 012 has no weight of its own
    And 011's weight is the sum of the two classes' weights
    """
    series, b = presets()
    s = series[0]
    s.used[2020].price_with["012"] = "011"
    per = calculator.preset_weights(s, {2020})["2020"]
    assert "012" not in per and per["011"] == pytest.approx(s.used[2020].weights["011"] + s.used[2020].weights["012"])


def test_calculator_refuses_inputs_that_dont_rebuild_the_series():
    """PY-SITEEXP-003: the calculator refuses inputs that don't rebuild the series

    Given preset series where one published month is changed by 0.5
    When the calculator file is built
    Then a FormatError saying the inputs "don't rebuild" the series is raised
    """
    series, b = presets()
    series[0].published["2020-05"] += 0.5
    with pytest.raises(FormatError, match="don't rebuild"):
        calculator.build(series, b, first_year=2019, digits=12)


def write_outputs(tmp_path):
    b = blocks()
    groups = [("B", "Q1"), ("B", "Q5"), ("all", "all")]
    k = baskets(groups)
    series = [
        index.build(None, g, q, blocks=b, baskets=k, first_year=None, options=dict(o))
        for o in ({}, {"weights_timing": "U"})
        for g, q in groups
    ]
    folder = tmp_path / "out" / "gr" / "m1"
    output.write(tmp_path / "out", series, [], {}, b)
    availability.write(folder, availability.build([availability.Summary.of(s) for s in series]))
    con = duckdb.connect()
    for table in output.TABLES:
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{(folder / f'{table}.parquet').as_posix()}'")
    return con, series


def test_series_file_holds_published_values_on_one_month_axis(tmp_path):
    """PY-SITEEXP-004: a setting's series file holds the published values on one month axis

    Given module 1 outputs written for three groups under the default setting
    And a standard error for the B Q1-Q5 annual gap in 2015-06
    When the series file is made for the default setting
    Then group B/Q1's annual rate at 2022-12 on the shared month axis is the series' rate rounded to 1 decimal
    And the gap's standard error sits at 2015-06 on that axis
    And the first flag is "less certain", with annual rates flagged up to 2011-12
    And the file serialises to plain JSON
    """
    con, series = write_outputs(tmp_path)
    default = dict(combinations.DEFAULT)
    se = {(site.slug(default), "B", "Q1-Q5", "RCH_A_GAP"): {"2015-06": 0.123}}
    f = site.series_file(con, default, se, {})
    q1 = f["groups"]["B/Q1"]
    i = site._months(f["start"], f["end"]).index("2022-12")
    expect = next(s for s in series if s.group == "Q1" and s.options["weights_timing"] == "N").rates()["2022-12"][
        "annual"
    ]
    assert q1["rch_a"][i] == round(expect, 1)
    assert f["gaps"]["B"]["se_a"][site._months(f["start"], f["end"]).index("2015-06")] == 0.123
    assert f["flags"][0]["code"] == "less certain" and f["flags"][0]["rch_a_to"] == "2011-12"
    assert json.dumps(f)  # plain JSON, no NaN


def test_a_rule_u_series_file_ends_with_its_surveys(tmp_path):
    """PY-SITEEXP-013: a weights timing "U" series file ends with its surveys

    Given module 1 outputs written with weights timing "U"
    When the series file is made for that setting
    Then it ends in 2024-12, with unit "I24"
    """
    con, _ = write_outputs(tmp_path)
    u = site.series_file(con, {**combinations.DEFAULT, "weights_timing": "U"}, {}, {})
    assert u["end"] == "2024-12" and u["groups"]["B/Q1"]["unit"] == "I24"


def test_downloads_add_a_csv_of_every_table_only_for_the_default_setting(tmp_path):
    """PY-SITEEXP-005: downloads add a CSV of every table only for the default setting

    Given module 1 outputs written for the default setting and for weights timing "U"
    When the download files are written for the non-default setting
    And for the default setting, with a checksum file
    Then the non-default downloads include the weights-used table as Parquet but not as CSV, and the rates as CSV
    And the default downloads also have the weights-used table as CSV
    And their checksum file lists the rates CSV and has 8 lines
    """
    con, _ = write_outputs(tmp_path)
    other = {**combinations.DEFAULT, "weights_timing": "U"}
    names = {p.name for p in site.downloads(con, other, tmp_path / "d1")}
    assert "m1_weights_used.parquet" in names and "m1_weights_used.csv" not in names and "m1_rates.csv" in names
    names = {p.name for p in site.downloads(con, combinations.DEFAULT, tmp_path / "d2")}
    assert "m1_weights_used.csv" in names
    sums = site.checksums(tmp_path / "d2").read_text(encoding="utf-8")
    assert "m1_rates.csv" in sums and len(sums.splitlines()) == 8


def test_official_rate_from_the_published_levels_of_two_files():
    # Each year's file holds its own months plus the previous December; only its own months count.
    """PY-SITEEXP-006: the official annual rate is computed from the levels in two years' files

    Given two years' CPI files, each holding its own months and the previous December
    And ELSTAT's published twelve-month rates for 2026-08 and 2026-09
    When the official rate is compared
    Then ours and ELSTAT's are both for 2026-09
    And ours is computed at full precision from the 2025-09 and 2026-09 levels (5.049184623573844, not 5.0467 from rounded indices)
    And both round to 5.0, with sources elstat:cpi07 and elstat:cpi05
    And the comparison says they agree

    Each year's file holds its own months plus the previous December; only its own months count.
    """
    b = {
        2025: {"TOTAL": {"2024-12": 1.0, "2025-09": 122.06030611018821, "2025-12": 122.5}},
        2026: {"TOTAL": {"2025-12": 999.0, "2026-08": 125.6, "2026-09": 128.223356317791}},
    }
    out = site.official_rate(b, {"2026-08": 0.037, "2026-09": 0.05049184623573861})
    ours, theirs = out["computed"], out["published"]
    # Full precision, as ELSTAT computes it: rounding the indices first would give 5.0467.
    assert ours["period"] == theirs["period"] == "2026-09"
    assert abs(ours["annual_rate_full"] - 5.049184623573844) < 1e-12
    assert ours["annual_rate"] == theirs["annual_rate"] == 5.0
    assert ours["source"] == "elstat:cpi07" and theirs["source"] == "elstat:cpi05"
    assert out["comparison"]["agree"] is True


def test_official_rate_reports_a_disagreement_instead_of_hiding_it():
    """PY-SITEEXP-007: a disagreement with the official rate is reported, not hidden

    Given levels that give 5.0% and a published rate of 5.1% for the same month
    When the official rate is compared
    Then ours is 5.0 and ELSTAT's 5.1
    And the comparison says they disagree, with a difference of -0.1
    """
    b = {2025: {"TOTAL": {"2025-09": 100.0}}, 2026: {"TOTAL": {"2026-09": 105.0}}}
    out = site.official_rate(b, {"2026-09": 0.051})
    assert out["computed"]["annual_rate"] == 5.0 and out["published"]["annual_rate"] == 5.1
    assert out["comparison"]["agree"] is False
    assert abs(out["comparison"]["difference"] + 0.1) < 1e-9


def test_official_rate_keeps_each_figure_in_its_own_month():
    # ELSTAT's table 05 a month ahead of table 07 (or behind): both shown, not compared.
    """PY-SITEEXP-008: our rate and the published one keep their own months

    Given levels up to 2026-09 and published rates up to 2026-10
    When the official rate is compared
    Then ours is for 2026-09 and ELSTAT's for 2026-10
    And no comparison is made

    ELSTAT's table 05 can be a month ahead of table 07 (or behind): both are shown, not compared.
    """
    b = {2025: {"TOTAL": {"2025-09": 100.0}}, 2026: {"TOTAL": {"2026-09": 105.0}}}
    out = site.official_rate(b, {"2026-09": 0.05, "2026-10": 0.06})
    assert out["computed"]["period"] == "2026-09" and out["published"]["period"] == "2026-10"
    assert "comparison" not in out


def test_official_rate_refuses_a_year_without_the_one_before():
    """PY-SITEEXP-009: the official rate refuses a year without the one before

    Given CPI levels for 2026 only
    When the official rate is compared
    Then a FormatError is raised
    """
    with pytest.raises(FormatError):
        site.official_rate({2026: {"TOTAL": {"2026-09": 128.2}}}, {"2026-09": 0.05})


def test_pps_factor_is_one_for_the_whole_year_and_least_bent_by_rounding():
    # Eurostat's EU-SILC 2025 limits for Greece (ilc_di01), in euros and in PPS, each rounded to a whole unit.
    """PY-SITEEXP-010: one EUR/PPS factor for the year, least bent by rounding

    Given Eurostat's 2025 EU-SILC income limits for Greece in euros and in PPS, each rounded to a whole unit
    When the PPS factor is worked out
    Then it is the sum of the euro limits over the sum of the PPS limits (47619 / 55400)
    And every limit in PPS times the factor is within 1 euro of the euro limit
    """
    eur = {"Q1": 7110, "Q2": 10269, "Q3": 13184, "Q4": 17056}
    pps = {"Q1": 8272, "Q2": 11947, "Q3": 15338, "Q4": 19843}
    f = site.pps_factor(eur, pps)
    assert f == pytest.approx(47619 / 55400)
    assert all(abs(eur[q] - f * pps[q]) <= 1 for q in eur)


def test_income_limits_file_names_the_missing_dataset_when_the_store_has_no_eurostat_limits():
    # The store's view is the union of the datasets it holds, so with no ilc_di01 rows its
    # columns (quant_inc, statinfo) don't exist: the export must say which dataset is missing,
    # not fail on an unknown column.
    """PY-SITEEXP-011: the income limits file names the missing Eurostat dataset

    Given a store whose observations hold our own HBS limits but no eurostat:ilc_di01 rows
    When the income limits file is made
    Then a FormatError naming eurostat:ilc_di01 is raised, not an unknown-column error

    The store's view is the union of the datasets it holds, so with no ilc_di01 rows its columns
    (quant_inc, statinfo) don't exist.
    """
    con = duckdb.connect()
    con.execute("""CREATE TABLE observations AS SELECT * FROM (VALUES
        ('oet-local:hbs_limits', 'k1', '2024', TIMESTAMP '2026-11-07 09:31:00', TIMESTAMP '2026-11-07 09:31:00',
         'new', 'B', 'GR', 'Q1', 'limit', NULL, 8000.0)
    ) AS t(dataset, key, ref_period, published_at, retrieved_at, status, grouping, geo, "group", measure,
           value_text, value)""")
    with pytest.raises(FormatError, match=r"eurostat:ilc_di01"):
        site.income_limits_file(con)


@pytest.mark.parametrize(
    "eur, pps, message",
    [
        ({"Q1": 7110, "Q2": 10269}, {"Q1": 8272, "Q2": 13000}, "one factor"),
        ({"Q1": 7110}, {"Q2": 8272}, "don't match"),
    ],
    ids=["ratios differ", "different quintiles"],
)
def test_pps_factor_refuses_limits_that_dont_share_one(eur, pps, message):
    """PY-SITEEXP-012: the PPS factor refuses limits that don't share one

    Given euro and PPS limits whose ratios differ by more than rounding allows, or limits of different quintiles
    When the PPS factor is worked out
    Then a FormatError says why: there is no "one factor", or the quintiles "don't match"
    """
    with pytest.raises(FormatError, match=message):
        site.pps_factor(eur, pps)


def test_m5_results_are_copied_with_checksums(tmp_path):
    """PY-SITEEXP-014: the consistency checks reach the site's data as written, with their checksums

    Given module5's results for Greece: one check and one question, with their CSV files
    When they are exported to the site's data, over an older copy holding a stale file
    Then checks.json is copied byte for byte, the CSVs go under downloads/, and the stale file is gone
    And SHA256SUMS lists every file
    And an outputs folder without module5 results exports nothing and says so
    """
    from traceconomics.module5.hbs import income_limits
    from traceconomics.module5.record import Check, Comparison
    from traceconomics.module5.run import write

    c = Check("gr-x", "gr", "percent", 1e-9, {"source": "a"}, {"source": "b"})
    c.comparisons = [Comparison("2001-01", 1.0, 1.0, True)]
    outputs, out = tmp_path / "outputs", tmp_path / "data"
    write([c], outputs, [income_limits({2024: {"Q1": 1.0}}, {2025: {"Q1": 2.0}})])
    stale = out / "v1" / "gr" / "m5" / "latest" / "old.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    site.export_m5(outputs, out, log=lambda *_: None)
    root = out / "v1" / "gr" / "m5" / "latest"
    assert (root / "checks.json").read_bytes() == (outputs / "gr" / "m5" / "checks.json").read_bytes()
    assert sorted(p.name for p in (root / "downloads").iterdir()) == ["gr-income-limits.csv", "gr-x.csv"]
    assert not stale.exists()
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8")
    assert "  checks.json" in sums and "  downloads/gr-x.csv" in sums
    said = []
    assert site.export_m5(tmp_path / "empty", tmp_path / "data2", log=said.append) == []
    assert said and "left out" in said[0]
