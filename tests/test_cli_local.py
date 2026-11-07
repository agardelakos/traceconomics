"""The command line's microdata commands (they need the `local` extra): what each prints and the
exit code it returns. As in test_cli.py, the work behind each command is replaced by a stand-in
with a known result; no survey data is read."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")

from traceconomics.archive.store import Archive  # noqa: E402
from clitools import no_store, run, setup  # noqa: E402,F401 - fixtures

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _archive_pufs(setup, years):
    archive = Archive(setup.cfg.archive_dir)
    for y in years:
        archive.store_bytes("elstat", f"puf-hbs-{y}", f"puf {y}".encode(), url=None, retrieved_at=NOW, ext=".zip")


def test_weights_run_defaults_to_every_archived_survey(setup, run, monkeypatch):
    """PY-CLI-038: weights run builds every archived survey year unless years are given

    Given an archive holding the surveys of 2019 and 2021
    When weights run is run without years, with 10 replicates
    And it is run for 2020 only
    Then the first run builds 2019 and 2021 with 10 replicates and prints one JSON line per year
    And after the second run only 2020 was asked for
    """
    from traceconomics.local import weights

    _archive_pufs(setup, (2019, 2021))
    asked = []

    def build(archive, years, replicates):
        asked.append((years, replicates))
        return [{"year": y, "result": "stored"} for y in years]
    monkeypatch.setattr(weights, "run", build)
    code, out = run("weights", "run", "--replicates", "10")
    assert code == 0 and [json.loads(line)["year"] for line in out.splitlines()] == [2019, 2021]
    assert asked == [([2019, 2021], 10)]
    run("weights", "run", "--years", "2020")
    assert asked[-1] == ([2020], 1000)


def test_bands_run_prints_the_summary_and_the_default_gap_errors(run, monkeypatch, no_store):
    """PY-CLI-039: bands run prints its summary and the standard error of the default setting's gap

    Given a bands run whose table holds the default setting's Q1-Q5 gap for two years and another setting's
    When bands run is run for the default combination
    Then only the default setting is computed
    And it prints the run's summary as JSON, without the table
    And it prints the gap's standard error by year for the default setting only
    """
    from traceconomics.local import bands
    from traceconomics.module1 import combinations

    default = dict(spending="purchases", imputed_rent="excluded", price_source="cpi", weights_timing="N",
                   tutoring="priced", grouping="B", unit="RCH_A_AVG_GAP")
    table = pd.DataFrame([default | {"ref_period": "2023", "se": 0.4}, default | {"ref_period": "2024", "se": 0.5},
                          default | {"price_source": "hicp", "ref_period": "2024", "se": 9.9}])
    seen = {}

    def bands_run(archive, con, replicates, only, log):
        seen.update(only=only, replicates=replicates)
        log("working")
        return {"result": "stored", "table": table}
    monkeypatch.setattr(bands, "run", bands_run)
    code, out = run("bands", "run", "--combinations", "default", "--replicates", "5")
    assert seen == {"only": [combinations.DEFAULT], "replicates": 5}
    lines = out.splitlines()
    assert code == 0 and lines[0] == "working" and json.loads(lines[1]) == {"result": "stored"}
    assert lines[2] == "Q1-Q5 gap, annual averages: standard error (pp) by year: {'2023': 0.4, '2024': 0.5}"


def test_mapping_build_prints_its_report(setup, run, monkeypatch, tmp_path):
    """PY-CLI-040: mapping build writes into the given folder and prints its report

    Given a mapping build that reports the tables it wrote
    When mapping build is run with --out
    Then the build reads the configured store and writes into the given folder
    And it prints the build's report as JSON
    """
    from traceconomics.local import mapping

    seen = {}
    monkeypatch.setattr(mapping, "build", lambda archive, store, out: seen.update(store=store, out=out)
                        or {"written": ["coicop_v1_2018.csv"]})
    code, out = run("mapping", "build", "--out", str(tmp_path / "data"))
    assert seen == {"store": setup.cfg.store_dir, "out": tmp_path / "data"}
    assert code == 0 and json.loads(out) == {"written": ["coicop_v1_2018.csv"]}


def _v2_row(year, group, passed, **kw):
    return SimpleNamespace(year=year, group=group, passed=passed, same_households=True, matched=10, compared=10,
                           excused=[], mismatches=kw.get("mismatches", []), uncovered=kw.get("uncovered"))


@pytest.mark.parametrize("strict_ok, code", [(True, 0), (False, 1)])
def test_check_v2_fails_only_on_a_strict_year(setup, run, monkeypatch, strict_ok, code):
    """PY-CLI-041: check v2 fails on a strict year's difference, never on a report-only year's

    Given archived surveys for 2017 and 2018, where 2018 is report-only
    And V2 results where 2018 differs and 2017 passes or differs
    And a band of 2017 whose label has a euro sign
    And standard errors that pass for 2017
    When check v2 is run
    Then 2018 is shown as "report only"
    And a strict year's difference is listed with the published and our figure
    And the euro sign is written as EUR
    And it ends with "V2 passed." and exit code 0 when 2017 passes, or "V2 FAILED." and 1
    """
    from traceconomics.local import puf, v2

    _archive_pufs(setup, (2017, 2018))
    assert 2018 in v2.REPORT_ONLY and 2017 not in v2.REPORT_ONLY
    rows = [_v2_row(2017, v2.ALL, strict_ok, mismatches=[] if strict_ok else [("01", "Food", 10.0, 11.0)], uncovered=0.05),
            _v2_row(2017, "up to 500 €", True), _v2_row(2018, v2.ALL, False, mismatches=[("02", "Drink", 1.0, 2.0)])]
    years_asked = []
    monkeypatch.setattr(v2, "run", lambda archive, years: years_asked.append(years) or rows)
    monkeypatch.setattr(v2, "published_cvs", lambda: {2017: {"cv": {"00": 1.0}, "source": "ELSTAT 2017"},
                                                     2016: {"cv": {}, "source": "not archived"}})
    monkeypatch.setattr(puf, "read", lambda archive, year: "survey")
    monkeypatch.setattr(v2, "cv_check", lambda survey, cv: SimpleNamespace(passed=True, design="strata", rows=[("00", 1.0, 1.1)]))
    got, out = run("check", "v2")
    assert years_asked == [[2017, 2018]]
    assert "2018: report only" in out and "Drink" not in out
    assert "up to 500 EUR" in out and "PUF lacks 5.0% of purchases" in out
    assert ("01 Food: published 10.0, ours 11.0" in out) is not strict_ok
    assert "2017: PASS (ELSTAT 2017; design strata)" in out and "not archived" not in out
    assert (got, out.strip().splitlines()[-1]) == ((0, "V2 passed.") if strict_ok else (1, "V2 FAILED."))


@pytest.mark.parametrize("passed, code", [(True, 0), (False, 1)])
def test_check_mapping_prints_each_comparison_and_the_cpi_report(run, monkeypatch, no_store, passed, code):
    """PY-CLI-042: check mapping prints both comparisons, each flag's verdict and the CPI report

    Given mapping comparisons that pass or fail, each flagging one code explained, one unexplained from the mapping
    And one not from the mapping
    And a CPI weights report
    When check mapping is run
    Then it compares 2023 with 2024 and 2014 with 2015, using each pair's explanations
    And each flag is shown as explained, NOT EXPLAINED or not from the mapping
    And the largest division difference and the CPI report are printed
    And it ends with "Mapping check passed." and exit code 0, or "Mapping check FAILED." and 1
    """
    from traceconomics.local import mapping_check as mc

    flags = [SimpleNamespace(code="0111", older=1.0, newer=1.5, usual=0.1, noise=0.1, exposure=0.5,
                             explanation="bread moved", from_mapping=True),
             SimpleNamespace(code="0112", older=1.0, newer=2.0, usual=0.1, noise=0.1, exposure=0.5,
                             explanation=None, from_mapping=True),
             SimpleNamespace(code="0113", older=1.0, newer=2.0, usual=0.1, noise=0.1, exposure=0.0,
                             explanation=None, from_mapping=False)]
    table = pd.DataFrame({"diff": [0.25, -0.5, 3.0]}, index=["01", "02", "0111"])
    pairs = []

    def compare(archive, older, newer, usual, reasons):
        pairs.append((older, newer, reasons))
        return SimpleNamespace(passed=passed, table=table, flags=flags)
    monkeypatch.setattr(mc, "usual_change", lambda archive: {})
    monkeypatch.setattr(mc, "explained", lambda: {"2023-2024": {"0111": "bread moved"}})
    monkeypatch.setattr(mc, "compare", compare)
    monkeypatch.setattr(mc, "cpi_report", lambda archive, con: pd.DataFrame({"division": ["01"], "mean_abs": [1.5]}))
    got, out = run("check", "mapping")
    assert pairs == [(2023, 2024, {"0111": "bread moved"}), (2014, 2015, {})]
    assert "divisions within 0.50 pp; 3 flagged" in out
    assert "0111: 1.00% -> 1.50%" in out and "explained: bread moved" in out
    assert "0112:" in out and "NOT EXPLAINED" in out and "not from the mapping" in out
    assert "mean_abs" in out
    assert (got, out.strip().splitlines()[-1]) == ((0, "Mapping check passed.") if passed else (1, "Mapping check FAILED."))


def test_check_hospital_prints_the_effect_of_putting_hospitals_back(run, monkeypatch, no_store):
    """PY-CLI-043: check hospital prints each survey's hospital share and the change it makes

    Given a hospital check with one survey, one group's change and the gap's change
    When check hospital is run
    Then it prints the survey's hospital share of purchases and its bands
    And the group's change and the gap's change, each with three decimals and a sign
    And it exits with code 0 (a report)
    """
    from traceconomics.local import hospital_check

    monkeypatch.setattr(hospital_check, "run", lambda archive, con: {
        "surveys": {2010: {"hospital_share_of_purchases": 0.012, "bands": "5 bands"}},
        "series": {"B Q1": {2011: 0.0123}}, "gap_change": {2011: -0.004}})
    code, out = run("check", "hospital")
    assert code == 0
    assert "survey 2010: 1.2% of purchases; 5 bands" in out
    assert "B Q1: 2011 +0.012" in out and "Change in the Q1-Q5 gap (pp): 2011 -0.004" in out
