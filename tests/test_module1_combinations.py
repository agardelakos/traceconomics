"""Every combination of the options: the settings, the output labels and flags, and the
availability table, on made-up prices and baskets."""

import json

import pytest

from traceconomics.module1 import availability, combinations, index, output
from traceconomics.module1.schedule import FINAL, Entry
from traceconomics.module1.weights_used import Basket, Used


def blocks():
    b = {}
    for y in range(2008, 2027):
        last = 9 if y == 2026 else 12
        b[y] = {c: {f"{y - 1}-12": 100.0, **{f"{y}-{m:02d}": 100 + m * k for m in range(1, last + 1)}}
                for c, k in (("01", 0.6), ("04", 0.3), ("10", 0.4))}
    return b


def baskets():
    shares = {"01": 0.5, "04": 0.45, "10501": 0.05}
    tiers = dict.fromkeys(shares, "normal")
    return {(h, g, q): Basket(dict(shares), dict(tiers)) for h in range(2008, 2025) for g, q in (("B", "Q1"), ("B", "Q5"))}


def test_48_settings_with_the_default_first():
    s = combinations.settings()
    assert len(s) == 48 and s[0] == combinations.DEFAULT
    assert len({combinations.label(x) for x in s}) == 48
    assert len(combinations.GROUPS) == 21


def test_quality_flags_follow_the_price_source():
    q = output.quality
    assert q("I25", "2010-12") == "less certain" and q("I25", "2011-01") == ""
    assert q("I25", "2014-12", "hicp") == "coarser detail" and q("I25", "2015-01", "hicp") == ""
    assert q("RCH_A", "2015-12", "hicp") == "coarser detail" and q("RCH_A", "2016-01", "hicp") == ""
    assert q("RCH_M", "2015-01", "hicp") == "coarser detail" and q("RCH_M", "2015-02", "hicp") == ""
    assert q("RCH_A_AVG", "2015", "hicp") == "coarser detail" and q("SHARE", "2015", "hicp") == ""


def test_small_cells_are_published_only_inside_a_rest_row():
    u = Used(Entry(2020, 2019, FINAL, "2020-01", "t"),
             {"01111": 0.1, "01112": 0.2, "01113": 0.3, "0112": 0.4},
             {"01111": "0111", "01112": "0111"}, small={"01111": "0111", "01112": "0111"})
    w = output.published_weights(u)
    assert set(w) == {"0111_REST", "01113", "0112"}
    assert w["0111_REST"] == (pytest.approx(0.3), "0111", 2)
    assert w["01113"][2] == 1
    assert sum(v for v, _, _ in w.values()) == pytest.approx(1.0)


def test_series_carry_their_options_and_rule_u_ends_with_its_surveys():
    b, k = blocks(), baskets()
    n = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None)
    u = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None, options={"weights_timing": "U"})
    f = index.build(None, "B", "Q1", blocks=b, baskets=k, first_year=None, options={"weights_timing": "F"})
    assert n.options == index.DEFAULT_OPTIONS and n.index_unit == "I25"
    assert u.options["weights_timing"] == "U" and max(u.published) == "2024-12" and u.index_unit == "I24"
    assert min(f.published) == "2010-12"                       # Rule F's first year is 2011
    rows = output.rows([n, u])
    assert {r["weights_timing"] for r in rows["m1_index"]} == {"N", "U"}
    assert {r["unit"] for r in rows["m1_index"]} == {"I25", "I24"}


def test_availability_greys_out_what_a_rule_cannot_cover(tmp_path):
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
    assert n["footnotes"]["hospital"]["annual_rates"] == ["2009-12", "2016-11"]    # weights from surveys 2008-2014
    assert n["footnotes"]["hospital"]["annual_averages"] == ["2010", "2016"]
    uf = next(s for s in table["series"] if s["weights_timing"] == "U")
    assert uf["footnotes"]["hospital"]["annual_rates"][1] == "2015-11"
    assert uf["footnotes"]["lockdown"]["index_years"] == [2020]
    paths = availability.write(tmp_path, table)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["fixed"]
    assert "rule_u_end" in paths[1].read_text(encoding="utf-8")


def test_a_rest_row_with_one_cell_is_flagged_low_reliability():
    s = index.build(None, "B", "Q1", blocks=blocks(), baskets=baskets(), first_year=None)
    u = s.used[2015]
    u.small = {"10501": "105"}
    rows = [r for r in output.series_rows(s) if r[0] == "m1_weights_used" and r[1]["ref_period"] == "2015"]
    rest = [r for _, r in rows if r["coicop18"] == "105_REST"]
    assert rest and rest[0]["quality"] == "low reliability"


def test_code_fingerprint_ignores_line_endings(monkeypatch, tmp_path):
    # The same code checked out on Windows (CRLF) and on Linux (LF) must give the same fingerprint.
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


def test_published_json_has_lf_line_endings(tmp_path):
    # Python on Windows writes CRLF unless told otherwise; published files must be byte-identical
    # whichever machine wrote them.
    from traceconomics.module1 import output

    path = output.write_metadata(tmp_path, first_period="2008-12", last_period="2026-09", manifest={})
    data = path.read_bytes()
    assert bytes([10]) in data and bytes([13]) not in data
