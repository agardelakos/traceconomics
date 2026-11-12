"""Every combination of the options: the settings, the output labels and flags, and the
availability table, on made-up prices and baskets."""

import json
from pathlib import Path

import pytest

from traceconomics.module1 import availability, combinations, index, output
from traceconomics.module1.schedule import FINAL, Entry
from traceconomics.module1.weights_used import Basket, Used

pytestmark = pytest.mark.unit


def blocks():
    b = {}
    for y in range(2008, 2027):
        last = 9 if y == 2026 else 12
        b[y] = {
            c: {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * k for m in range(1, last + 1)}}
            for c, k in (("01", 0.6), ("04", 0.3), ("10", 0.4))
        }
    return b


def baskets():
    shares = {"01": 0.5, "04": 0.45, "10501": 0.05}
    tiers = dict.fromkeys(shares, "normal")
    return {
        (h, g, q): Basket(dict(shares), dict(tiers)) for h in range(2008, 2025) for g, q in (("B", "Q1"), ("B", "Q5"))
    }


def test_48_settings_with_the_default_first():
    """PY-COMBO-001: 48 settings, with the default first

    Given the module 1 options
    When every setting is listed
    Then there are 48, the first being the default
    And each has its own label
    And there are 27 groups: 3 groupings of five fifths, all, 3 tenures, 2 pensioner groups and 6 household types
    """
    s = combinations.settings()
    assert len(s) == 48 and s[0] == combinations.DEFAULT
    assert len({combinations.label(x) for x in s}) == 48
    assert len(combinations.GROUPS) == 27  # 3 x 5 fifths, all, 3 tenures, 2 pensioner groups, 6 household types


def test_quality_flags_follow_the_price_source():
    """PY-COMBO-002: quality flags follow the price source

    Given periods on each side of the price sources' limits
    When the quality flag of each measure is read
    Then the index is "less certain" up to 2010-12 and unflagged from 2011-01
    And on HICP prices the index is "coarser detail" up to 2014-12, the annual rate up to 2015-12, the monthly rate up to 2015-01 and the annual average for 2015
    And each is unflagged after that, and shares for 2015 are never flagged
    """
    q = output.quality
    assert q("I25", "2010-12") == "less certain" and q("I25", "2011-01") == ""
    assert q("I25", "2014-12", "hicp") == "coarser detail" and q("I25", "2015-01", "hicp") == ""
    assert q("RCH_A", "2015-12", "hicp") == "coarser detail" and q("RCH_A", "2016-01", "hicp") == ""
    assert q("RCH_M", "2015-01", "hicp") == "coarser detail" and q("RCH_M", "2015-02", "hicp") == ""
    assert q("RCH_A_AVG", "2015", "hicp") == "coarser detail" and q("SHARE", "2015", "hicp") == ""


def test_small_cells_are_published_only_inside_a_rest_row():
    """PY-COMBO-003: small cells are published only inside a rest row

    Given a year's weights where two small subclasses are priced with their class
    When the published weights are made
    Then the two small cells appear only as one "0111_REST" row, of weight 0.3, under 0111, covering 2 cells
    And the other subclass covers 1 cell
    And the published weights sum to 1
    """
    u = Used(
        Entry(2020, 2019, FINAL, "2020-01", "t"),
        {"01111": 0.1, "01112": 0.2, "01113": 0.3, "0112": 0.4},
        {"01111": "0111", "01112": "0111"},
        small={"01111": "0111", "01112": "0111"},
    )
    w = output.published_weights(u)
    assert set(w) == {"0111_REST", "01113", "0112"}
    assert w["0111_REST"] == (pytest.approx(0.3), "0111", 2)
    assert w["01113"][2] == 1
    assert sum(v for v, _, _ in w.values()) == pytest.approx(1.0)


def test_series_carry_their_options_and_rule_u_ends_with_its_surveys():
    """PY-COMBO-004: series carry their options, and rule U ends with its surveys

    Given made-up prices and baskets for B/Q1
    When the series is built with the default options, with weights timing "U" and with weights timing "F"
    And the default and "U" series are turned into output rows
    Then the default series has the default options and unit I25
    And the "U" series ends at 2024-12, with unit I24
    And the "F" series starts at 2010-12, since its first year is 2011
    And the index rows carry weights timing N and U, and units I25 and I24
    """
    b, k = blocks(), baskets()
    n = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None)
    u = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None, options={"weights_timing": "U"})
    f = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None, options={"weights_timing": "F"})
    assert n.options == index.DEFAULT_OPTIONS and n.index_unit == "I25"
    assert u.options["weights_timing"] == "U" and max(u.published) == "2024-12" and u.index_unit == "I24"
    assert min(f.published) == "2010-12"  # Rule F's first year is 2011
    rows = output.rows([n, u])
    assert {r["weights_timing"] for r in rows["m1_index"]} == {"N", "U"}
    assert {r["unit"] for r in rows["m1_index"]} == {"I25", "I24"}


def test_availability_greys_out_what_a_rule_cannot_cover(tmp_path):
    """PY-COMBO-005: availability greys out what a rule can't cover

    Given series for B/Q1 and B/Q5 under weights timing N, F and U
    When the availability table is built and written
    Then rule F is greyed with reason "rule_f_start" for annual rates from 2009-12 to 2011-11
    And rule U is greyed with reason "rule_u_end" for the index from 2025-01 to 2026-09, its text naming 2024
    And the default series has the hospital footnote for annual rates 2009-12 to 2016-11 and annual averages 2010 to 2016 (weights from surveys 2008-2014)
    And the "U" series' hospital footnote ends at 2015-11 and its lockdown footnote covers index year 2020
    And the first written file holds the fixed part and the second names "rule_u_end"
    """
    b, k = blocks(), baskets()
    summaries = []
    for rule in ("N", "F", "U"):
        for q in ("Q1", "Q5"):
            s = index.build(None, "B", q, blocks=b, baskets=k, first_year=None, options={"weights_timing": rule})
            summaries.append(availability.Summary.of(s))
    table = availability.build(summaries)
    f, u = table["options"]["weights_timing"]["F"], table["options"]["weights_timing"]["U"]
    assert f["greyed"][0]["reason"] == "rule_f_start" and f["greyed"][0]["annual_rates"] == ["2009-12", "2011-11"]
    assert u["greyed"][0]["reason"] == "rule_u_end" and u["greyed"][0]["index"] == ["2025-01", "2026-09"]
    assert "2024" in u["greyed"][0]["text"]
    n = next(s for s in table["series"] if s["weights_timing"] == "N")
    assert n["footnotes"]["hospital"]["annual_rates"] == ["2009-12", "2016-11"]  # weights from surveys 2008-2014
    assert n["footnotes"]["hospital"]["annual_averages"] == ["2010", "2016"]
    uf = next(s for s in table["series"] if s["weights_timing"] == "U")
    assert uf["footnotes"]["hospital"]["annual_rates"][1] == "2015-11"
    assert uf["footnotes"]["lockdown"]["index_years"] == [2020]
    paths = availability.write(tmp_path, table)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["fixed"]
    assert "rule_u_end" in paths[1].read_text(encoding="utf-8")


def test_an_option_whose_source_publishes_later_is_greyed_for_the_months_it_lacks():
    """PY-COMBO-018: an option whose source publishes later is greyed for the months it lacks

    Given series for B/Q1 under the CPI to 2026-09 and under the HICP to 2026-08, as for the week every month between ELSTAT's CPI and Eurostat's item indices
    When the availability table is built
    Then the HICP is greyed with reason "ends_earlier" for the index and annual rates of 2026-09
    And its text names 2026-09, the first month it doesn't have yet
    And the CPI is not greyed
    """
    cpi = blocks()
    hicp = {y: {c: {p: v for p, v in s.items() if p != "2026-09"} for c, s in b.items()} for y, b in blocks().items()}
    k = baskets()
    summaries = [
        availability.Summary.of(
            index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None, options={"price_source": src})
        )
        for src, b in (("cpi", cpi), ("hicp", hicp))
    ]
    table = availability.build(summaries)
    h, c = table["options"]["price_source"]["hicp"], table["options"]["price_source"]["cpi"]
    assert [g["reason"] for g in h["greyed"]] == ["ends_earlier"]
    assert h["greyed"][0]["index"] == ["2026-09", "2026-09"] and h["greyed"][0]["annual_rates"] == [
        "2026-09",
        "2026-09",
    ]
    assert "2026-09" in h["greyed"][0]["text"]
    assert c["greyed"] == []


@pytest.mark.repository
def test_every_reason_has_a_text_in_both_site_languages():
    """PY-COMBO-019: every reason the availability table can give has a text in both site languages

    Given the reasons the availability table can give
    When the site's English and Greek language files are read
    Then each language file has a "reason.<code>" text for every one of them

    The site looks a greyed option's reason up by its code and stops with "missing text" if there
    is none, so a reason without a text breaks the Explore page for that option.
    """
    root = Path(__file__).resolve().parents[1] / "site" / "src" / "i18n"
    for lang in ("en", "el"):
        texts = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
        assert sorted(c for c in availability.REASONS if f"reason.{c}" not in texts) == [], lang


def test_a_rest_row_with_one_cell_is_flagged_low_reliability():
    """PY-COMBO-006: a rest row with one cell is flagged low reliability

    Given a series whose 2015 weights have one small cell (10501) priced with its group
    When its weights-used rows are written
    Then the 2015 row "105_REST" is flagged "low reliability"
    """
    s = index.build(None, "B", "Q1", blocks=blocks(), baskets=baskets(), first_year=None)
    u = s.used[2015]
    u.small = {"10501": "105"}
    rows = [r for r in output.series_rows(s) if r[0] == "m1_weights_used" and r[1]["ref_period"] == "2015"]
    rest = [r for _, r in rows if r["coicop18"] == "105_REST"]
    assert rest and rest[0]["quality"] == "low reliability"


def test_code_fingerprint_ignores_line_endings(monkeypatch, tmp_path):
    # The same code checked out on Windows (CRLF) and on Linux (LF) must give the same fingerprint.
    """PY-COMBO-007: the code fingerprint ignores line endings

    Given a made-up package with one source file with LF line endings, and its fingerprint
    When the file is rewritten with CRLF line endings
    And then rewritten with a changed line
    Then the CRLF file gives the same fingerprint
    And the changed file gives a different one

    The same code checked out on Windows (CRLF) and on Linux (LF) must give the same fingerprint.
    """
    from traceconomics.module1 import output

    pkg = tmp_path / "fakepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_bytes(b"")
    (pkg / "a.py").write_bytes(b"x = 1\ny = 2\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(output, "CODE", {"fakepkg": ["a.py"]})
    lf = output.code_fingerprint()
    (pkg / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert output.code_fingerprint() == lf
    (pkg / "a.py").write_bytes(b"x = 1\ny = 3\n")
    assert output.code_fingerprint() != lf


def test_the_published_metadata_has_lf_line_endings(tmp_path):
    """PY-COMBO-008: the published metadata has LF line endings

    Given an output folder
    When the metadata file is written
    Then it contains LF and no CR

    Python on Windows writes CRLF unless told otherwise; published files must be byte-identical
    whichever machine wrote them.
    """
    from traceconomics.module1 import output

    path = output.write_metadata(tmp_path, first_period="2008-12", last_period="2026-09", manifest={})
    data = path.read_bytes()
    assert bytes([10]) in data and bytes([13]) not in data


def test_parquet_is_written_with_one_thread():
    # DuckDB reads a large CSV in parallel chunks and the Parquet row groups follow them: on the real
    # contributions table (2.8 million rows) 2 threads gave a different file from 1 or 16. Published
    # files must be byte-identical wherever they are built, so they are written with one thread.
    """PY-COMBO-009: Parquet is written with one thread

    Given the connection used to write Parquet
    When its thread setting is read
    Then it is 1

    DuckDB reads a large CSV in parallel chunks and the Parquet row groups follow them: on the real
    contributions table (2.8 million rows) 2 threads gave a different file from 1 or 16. Published
    files must be byte-identical wherever they are built, so they are written with one thread.
    """
    from traceconomics.module1 import output

    con = output.parquet_connection()
    assert con.execute("SELECT current_setting('threads')").fetchone()[0] == 1
