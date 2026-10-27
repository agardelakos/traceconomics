"""The website's data files, on made-up series: the calculator file rebuilds the series exactly,
and the per-setting files carry what the outputs hold."""

import json

import duckdb
import pytest

from traceconomics.checks import FormatError
from traceconomics.export import calculator, site
from traceconomics.module1 import availability, combinations, index, output
from traceconomics.module1.weights_used import Basket


def blocks():
    b = {}
    for y in range(2008, 2027):
        last = 9 if y == 2026 else 12
        b[y] = {c: {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * k + (y % 3) * 0.17 * m for m in range(1, last + 1)}}
                for c, k in (("011", 0.61), ("012", 0.23), ("041", 0.31), ("07", 0.83))}
    return b


def baskets(groups):
    out = {}
    for h in range(2008, 2025):
        for n, (g, q) in enumerate(groups):
            shares = {"01": 0.4, "011": 0.3 + 0.01 * n, "012": 0.1 - 0.01 * n, "04": 0.25, "041": 0.25,
                      "07": 0.35 - 0.001 * h % 7}
            out[(h, g, q)] = Basket(shares, dict.fromkeys(shares, "normal"))
    return out


def presets():
    b, k = blocks(), baskets(calculator.PRESETS)
    return [index.build(None, g, q, blocks=b, baskets=k) for g, q in calculator.PRESETS], b


def test_calculator_file_rebuilds_every_preset_exactly():
    series, b = presets()
    data = calculator.build(series, b, first_year=2019, digits=12)
    assert data["first_year"] == 2019 and set(data["presets"]) == {f"{g}/{q}" for g, q in calculator.PRESETS}
    codes = data["codes"]
    w = {y: {codes[i]: v for i, v in rows} for y, rows in data["presets"]["B/Q1"].items()}
    r = {y: {codes[i]: v for i, v in rows} for y, rows in data["ratios"].items()}
    rebuilt = calculator.rebuild(w, r, 2019)
    s = next(x for x in series if (x.grouping, x.group) == ("B", "Q1"))
    assert all(round(v, 2) == s.published[p] for p, v in rebuilt.items() if p >= "2019-01")
    assert max(len(v) for _, v in data["ratios"]["2026"]) == 9                 # months not out yet are left off


def test_calculator_weights_are_summed_by_the_index_that_prices_them():
    series, b = presets()
    s = series[0]
    s.used[2020].price_with["012"] = "011"
    per = calculator.preset_weights(s, {2020})["2020"]
    assert "012" not in per and per["011"] == pytest.approx(s.used[2020].weights["011"] + s.used[2020].weights["012"])


def test_calculator_refuses_inputs_that_dont_rebuild_the_series():
    series, b = presets()
    series[0].published["2020-05"] += 0.5
    with pytest.raises(FormatError, match="don't rebuild"):
        calculator.build(series, b, first_year=2019, digits=12)


def write_outputs(tmp_path):
    b = blocks()
    groups = [("B", "Q1"), ("B", "Q5"), ("all", "all")]
    k = baskets(groups)
    series = [index.build(None, g, q, blocks=b, baskets=k, first_year=None, options=dict(o))
              for o in ({}, {"weights_timing": "U"}) for g, q in groups]
    folder = tmp_path / "out" / "gr" / "m1"
    output.write(tmp_path / "out", series, [], {}, b)
    availability.write(folder, availability.build([availability.Summary.of(s) for s in series]))
    con = duckdb.connect()
    for table in output.TABLES:
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{(folder / f'{table}.parquet').as_posix()}'")
    return con, series


def test_series_file_holds_published_values_on_one_month_axis(tmp_path):
    con, series = write_outputs(tmp_path)
    default = dict(combinations.DEFAULT)
    se = {(site.slug(default), "B", "Q1-Q5", "RCH_A_GAP"): {"2015-06": 0.123}}
    f = site.series_file(con, default, se, {})
    q1 = f["groups"]["B/Q1"]
    i = site._months(f["start"], f["end"]).index("2022-12")
    expect = next(s for s in series if s.group == "Q1" and s.options["weights_timing"] == "N").rates()["2022-12"]["annual"]
    assert q1["rch_a"][i] == round(expect, 1)
    assert f["gaps"]["B"]["se_a"][site._months(f["start"], f["end"]).index("2015-06")] == 0.123
    assert f["flags"][0]["code"] == "less certain" and f["flags"][0]["rch_a_to"] == "2011-12"
    u = site.series_file(con, {**default, "weights_timing": "U"}, {}, {})
    assert u["end"] == "2024-12" and u["groups"]["B/Q1"]["unit"] == "I24"
    assert json.dumps(f)                                                       # plain JSON, no NaN


def test_downloads_csv_only_for_core_tables_except_the_default(tmp_path):
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
    b = {2025: {"TOTAL": {"2024-12": 1.0, "2025-09": 122.06030611018821, "2025-12": 122.5}},
         2026: {"TOTAL": {"2025-12": 999.0, "2026-08": 125.6, "2026-09": 128.223356317791}}}
    out = site.official_rate(b, {"2026-08": 0.037, "2026-09": 0.05049184623573861})
    ours, theirs = out["computed"], out["published"]
    # Full precision, as ELSTAT computes it: rounding the indices first would give 5.0467.
    assert ours["period"] == theirs["period"] == "2026-09"
    assert abs(ours["annual_rate_full"] - 5.049184623573844) < 1e-12
    assert ours["annual_rate"] == theirs["annual_rate"] == 5.0
    assert ours["source"] == "elstat:cpi07" and theirs["source"] == "elstat:cpi05"
    assert out["comparison"]["agree"] is True


def test_official_rate_reports_a_disagreement_instead_of_hiding_it():
    b = {2025: {"TOTAL": {"2025-09": 100.0}}, 2026: {"TOTAL": {"2026-09": 105.0}}}
    out = site.official_rate(b, {"2026-09": 0.051})
    assert out["computed"]["annual_rate"] == 5.0 and out["published"]["annual_rate"] == 5.1
    assert out["comparison"]["agree"] is False
    assert abs(out["comparison"]["difference"] + 0.1) < 1e-9


def test_official_rate_keeps_each_figure_in_its_own_month():
    # ELSTAT's table 05 a month ahead of table 07 (or behind): both shown, not compared.
    b = {2025: {"TOTAL": {"2025-09": 100.0}}, 2026: {"TOTAL": {"2026-09": 105.0}}}
    out = site.official_rate(b, {"2026-09": 0.05, "2026-10": 0.06})
    assert out["computed"]["period"] == "2026-09" and out["published"]["period"] == "2026-10"
    assert "comparison" not in out


def test_official_rate_refuses_a_year_without_the_one_before():
    with pytest.raises(FormatError):
        site.official_rate({2026: {"TOTAL": {"2026-09": 128.2}}}, {"2026-09": 0.05})
