"""Past figures typed into the site's text, against small made-up data files."""

import json
from pathlib import Path

import duckdb
import pytest

from traceconomics import quoted_figures as qf

pytestmark = pytest.mark.unit

ALLOW = Path(__file__).parents[1] / "site" / "src" / "i18n" / "figures-allow.json"
DEFAULT = "purchases_excluded_cpi_N_priced"
OTHER = "purchases_excluded_hicp_N_priced"


def data(tmp_path: Path, gaps: dict[str, float], other: dict[str, float] | None = None, rents=None) -> Path:
    """A site data folder: the default setting's Q1-Q5 gap by month (and another setting's), and an
    m5 rent series."""
    root = tmp_path / "data"
    m1 = root / "v1" / "gr" / "m1" / "latest"
    m1.mkdir(parents=True)
    (m1 / "settings.json").write_text(json.dumps({"default": DEFAULT}), encoding="utf-8")
    for slug, series in ((DEFAULT, gaps), (OTHER, other or gaps)):
        folder = m1 / "downloads" / slug
        folder.mkdir(parents=True)
        con = duckdb.connect()
        con.execute('CREATE TABLE r (grouping TEXT, "group" TEXT, unit TEXT, ref_period TEXT, value TEXT)')
        con.executemany(
            "INSERT INTO r VALUES ('B', 'Q1-Q5', 'RCH_A_GAP', ?, ?)", [[p, repr(v)] for p, v in series.items()]
        )
        con.execute(f"COPY r TO '{(folder / 'm1_rates.parquet').as_posix()}' (FORMAT parquet)")
    m5 = root / "v1" / "gr" / "m5" / "latest" / "downloads"
    m5.mkdir(parents=True)
    rows = "".join(f"{p},cpi,{v}\n" for p, v in (rents or {"2015": 100.0, "2021": 92.27, "2024": 102.92}).items())
    (m5 / "gr-rent-change.csv").write_text("period,source,value\n" + rows, encoding="utf-8")
    return root


GAPS = {"2022-03": 2.1, "2022-04": 2.46, "2022-05": 2.2}
PEAK = {"m1": {"setting": "default", "grouping": "B", "group": "Q1-Q5", "unit": "RCH_A_GAP", "period": "2022-04"}}


def entry(*checks, kind="past"):
    return {"id": "glossary/gap.md#intro", "kind": kind, "en": [c["figure"] for c in checks], "checks": list(checks)}


@pytest.mark.parametrize(
    "figure, number, decimals",
    [
        ("2.5 points", "2.5", 1),
        ("−1.6 points", "-1.6", 1),
        ("+1.4 points", "1.4", 1),
        ("8%", "8", 0),
        ("€7 110", "7110", 0),
    ],
)
def test_a_figure_is_read_as_written(figure, number, decimals):
    """PY-QFIG-001: a figure's number and decimals are read as the English text writes it

    Given figures with a typographic minus, a plus sign, no decimals, or a space as thousands separator
    When the number is read
    Then the sign, the digits and the number of decimals are kept
    """
    got, places = qf.written(figure)
    assert (str(got), places) == (number, decimals)


def test_a_figure_the_data_still_give_passes_and_a_revised_one_fails(tmp_path):
    """PY-QFIG-002: a past figure passes while the data, rounded as written, give it, and fails once they don't

    Given the text's "2.5 points", the default setting's gap in April 2022, its peak
    When the data give 2.46 (2.5 as written), then 2.44, then 2.46 with May higher
    Then the first passes
    And the second fails, naming the text's figure and the data's
    And the third fails, saying where the series now peaks
    """
    figure = entry({"figure": "2.5 points", **PEAK, "peak": True})
    assert qf.check(data(tmp_path / "a", GAPS), [figure]) == []
    assert qf.check(data(tmp_path / "b", {**GAPS, "2022-04": 2.44}), [figure]) == [
        "glossary/gap.md#intro: the text says 2.5 points, the data now say 2.4"
    ]
    (problem,) = qf.check(data(tmp_path / "c", {**GAPS, "2022-05": 2.6}), [figure])
    assert "peaks at 2022-05 (2.60), not at 2022-04" in problem


def test_differences_largest_values_and_changes_are_recomputed(tmp_path):
    """PY-QFIG-003: differences between settings, the largest over periods, percent changes and sizes are recomputed

    Given the default setting's gap and another setting's, differing by 0.3, 0.06 and -0.07
    And a rent index at 100 in 2015, 92.27 in 2021 and 102.92 in 2024
    When figures for "at most 0.07 points" (largest of the two settings' difference), "the largest of two such differences", "fell by about 8%" and "3% above 2015" are checked
    Then each passes, and "at most 0.06 points" fails because the largest is 0.07
    And a period missing from the data fails as not recomputable
    """
    other = {"2022-03": 1.8, "2022-04": 2.40, "2022-05": 2.27}
    root = data(tmp_path, GAPS, other)
    most = {"m1": {k: v for k, v in PEAK["m1"].items() if k != "period"}, "minus": {"setting": OTHER}, "most": True}
    checks = [
        {"figure": "0.3 points", **most},
        {"figure": "0.3 points", "largest_of": [most, {**most, "minus": {"setting": "default"}}]},
        {"figure": "8%", "m5": "gr-rent-change", "source": "cpi", "period": "2021", "change_from": "2015", "abs": True},
        {"figure": "3%", "m5": "gr-rent-change", "source": "cpi", "period": "2024", "change_from": "2015"},
    ]
    assert qf.check(root, [entry(*checks)]) == []
    tight = {**most, "minus": {"setting": OTHER}}
    root2 = data(tmp_path / "2", GAPS, {**other, "2022-03": 2.1})  # largest now 0.07, in May
    assert qf.check(root2, [entry({"figure": "0.06 points", **tight})]) == [
        "glossary/gap.md#intro: the text says 0.06 points, the data now say 0.07"
    ]
    (gone,) = qf.check(root, [entry({"figure": "8%", **checks[2], "period": "2025"})])
    assert "can't be recomputed (no value for 2025)" in gone


def test_the_list_says_where_every_past_figure_comes_from():
    """PY-QFIG-004: a past entry must name, figure by figure, a data check or its datasets with a reason

    Given past entries whose checks miss a figure, name sources without a reason, or check a range against one value
    And entries of other kinds without checks
    When the list is checked
    Then each problem is named with its entry
    And the other kinds are left alone
    """
    entries = [
        {"id": "a", "kind": "past", "en": ["1%", "2%"], "checks": [{"figure": "1%", "sources": ["x"], "reason": "y"}]},
        {"id": "b", "kind": "past", "en": ["1%"], "checks": [{"figure": "1%", "sources": ["x"]}]},
        {"id": "c", "kind": "past", "en": ["1–2%"], "checks": [{"figure": "1–2%", **PEAK}]},
        {"id": "d", "kind": "rule", "en": ["100%"]},
    ]
    problems = qf.problems_in_list(entries)
    assert problems[0] == "a: its checks name ['1%'], its English figures are ['1%', '2%']"
    assert problems[1] == "b: 1%: neither a data check nor sources with a reason"
    assert problems[2].startswith("c: '1–2%': not one number")
    assert len(problems) == 3


def test_every_past_figure_on_the_site_says_where_it_comes_from():
    """PY-QFIG-005: every past figure in the site's allow-list has a data check or named datasets with a reason

    Given the site's figures-allow.json
    When the list is checked
    Then it has no problem
    And it has both kinds: figures the data recompute, and figures resting on named datasets
    """
    entries = qf.load(ALLOW)
    assert qf.problems_in_list(entries) == []
    checks = [c for e in entries if e["kind"] == "past" for c in e["checks"]]
    assert any("sources" in c for c in checks) and any("sources" not in c for c in checks)


def test_a_changed_dataset_names_the_figures_resting_on_it():
    """PY-QFIG-006: a changed dataset names each entry whose figures rest on it, by name or by prefix

    Given an entry resting on ELSTAT's 2025 table 07 and one on every survey weights table (a prefix)
    When the 2025 table 07 changes, then the 2024 weights table, then only an unrelated dataset
    Then the first names the first entry, the second the second, and the third nothing
    """
    quoted = {"rent": ["elstat/doc-554284"], "spending": ["oet-local/hbs-weights-gr-*"]}
    assert qf.changed_sources(quoted, {"elstat/doc-554284"}) == [
        "the text's figures in rent rest on elstat/doc-554284, which changed: read them again"
    ]
    assert qf.changed_sources(quoted, {"oet-local/hbs-weights-gr-2024"})[0].startswith("the text's figures in spending")
    assert qf.changed_sources(quoted, {"elstat/doc-585819"}) == []


@pytest.mark.parametrize(
    "value, decimals, text", [(0.125, 2, "0.13"), (2.5, 0, "3"), (-1.25, 1, "-1.3"), (2.44, 1, "2.4")]
)
def test_values_are_rounded_half_up_as_the_site_writes_them(value, decimals, text):
    """PY-QFIG-007: a recomputed value is rounded half away from zero, as the site writes figures, not half to even

    Given values exactly halfway between two written figures, and one that isn't
    When they are rounded to the figure's decimals
    Then halves go away from zero (0.125 to 0.13, 2.5 to 3, -1.25 to -1.3), where Python's round() would go to the even digit
    """
    assert str(qf.rounded(value, decimals)) == text


def test_the_datasets_behind_past_figures_are_listed_by_entry():
    """PY-QFIG-008: each past figure's entry is listed with the archived datasets its checks name

    Given an allow-list with a past figure whose two checks name three datasets (one twice), a past figure with a data check only, and a figure of another kind
    When the datasets behind the figures are listed
    Then only the first entry is listed, with its datasets once each and sorted
    """
    entries = [
        {"id": "a", "kind": qf.PAST, "checks": [{"sources": ["z:x", "e:y*"]}, {"sources": ["z:x", "b:c"]}]},
        {"id": "b", "kind": qf.PAST, "checks": [{"figure": "1.2"}]},
        {"id": "c", "kind": "other", "checks": [{"sources": ["z:x"]}]},
    ]
    assert qf.sources(entries) == {"a": ["b:c", "e:y*", "z:x"]}
