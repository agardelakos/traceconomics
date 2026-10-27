"""ELSTAT CPI table 05 (the overall index and its published twelve-month rate) on the real file,
and refusals on made-up variants of its layout."""

from pathlib import Path

import openpyxl
import pytest

from traceconomics.checks import FormatError
from traceconomics.sources.elstat.table05 import parse

FIX = Path(__file__).parent / "fixtures"
REAL = FIX / "elstat_cpi05_2026_09.xlsx"


def test_real_file_september_2026():
    t = parse(REAL)
    assert t.last == "2026-09"
    assert min(t.index) == "1959-01" and max(t.index) == "2026-09" and len(t.index) == 67 * 12 + 9
    assert min(t.rate) == "1960-01" and len(t.rate) == 66 * 12 + 9          # no rate in the first year
    assert t.rate["2026-09"] == 0.05049184623573861                          # full precision, a fraction
    assert t.index["2026-09"] == 128.223356317791                            # the same level as table 07
    assert "2026" not in t.annual_index and "2027" not in t.annual_index     # no average before December
    assert t.annual_rate["2025"] == pytest.approx(0.024816205454631677)


# Months where the published rate isn't the index ratio at full precision, in the September 2026
# file: June-December 1999 were published rounded to one decimal; June 2001's rate (3.9332%) doesn't
# follow from the two index levels (3.9239%), and rounding doesn't explain it.
ROUNDED_1999 = [f"1999-{m:02d}" for m in range(6, 13)]
UNEXPLAINED = ["2001-06"]


def test_published_rate_is_its_own_index_ratio_except_eight_months():
    t = parse(REAL)
    differ = []
    for period, rate in t.rate.items():
        y, m = period.split("-")
        if abs(rate - (t.index[period] / t.index[f"{int(y) - 1}-{m}"] - 1)) > 1e-12:
            differ.append(period)
    assert sorted(differ) == ROUNDED_1999 + UNEXPLAINED
    for period in ROUNDED_1999:
        y, m = period.split("-")
        assert rate_pct(t, period) == round((t.index[period] / t.index[f"1998-{m}"] - 1) * 100, 1)


def rate_pct(t, period):
    return round(t.rate[period] * 100, 10)


def made_up(tmp_path, *, title="TableV. Evolution of the twelve-month rates of change of the Overall CPI,"
            "during the years 1959-1960 (March)", base="Base Year :2020=100,0", header="Rate of change", months=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, title])
    ws.append([None] * 4 + [base])
    ws.append([None, " 1 9 5 9 ", None, " 1 9 6 0", None, " 1 9 6 1"])
    ws.append(["Month", "Index", header, "Index", header, "Index", header])
    ws.append([None])
    for k in months or range(1, 13):
        ws.append([k, 1.0 + k / 100, None, *((1.1 + k / 100, 0.01) if k <= 3 else (None, None)), None, None])
    ws.append([" Annual average", 1.05, None, None, None, None, None])
    path = tmp_path / "t05.xlsx"
    wb.save(path)
    return path


def test_made_up_file_parses(tmp_path):
    t = parse(made_up(tmp_path))
    assert t.last == "1960-03" and len(t.index) == 15 and sorted(t.rate) == ["1960-01", "1960-02", "1960-03"]


@pytest.mark.parametrize("change", [
    {"title": "Table IV. Monthly evolution of the Overall Consumer Price Index 1959-1960 (March)"},
    {"base": "Base Year :2009=100,0"},
    {"header": "Change"},
    {"months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 11]},
    {"title": "TableV. Evolution of the twelve-month rates of change of the Overall CPI, 1959-1960 (February)"},
])
def test_refuses_a_changed_layout(tmp_path, change):
    with pytest.raises(FormatError):
        parse(made_up(tmp_path, **change))
